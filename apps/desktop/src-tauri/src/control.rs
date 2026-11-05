use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::{
    fs,
    io::{Read, Write},
    net::{IpAddr, SocketAddr, TcpStream},
    path::{Path, PathBuf},
    time::{Duration, SystemTime, UNIX_EPOCH},
};

type Result<T> = std::result::Result<T, String>;
pub struct Control {
    pub profile: PathBuf,
}
#[derive(Deserialize)]
struct Session {
    profile_id: String,
    workspace_id: String,
    host: String,
}
struct Connection {
    session: Session,
    address: SocketAddr,
    token: String,
}

pub fn valid_id(id: &str, prefix: &str) -> Result<()> {
    if !id.starts_with(prefix)
        || id.len() > 84
        || id.len() <= prefix.len()
        || !id
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b == b'_' || b == b'-')
    {
        return Err("INVALID_ID".into());
    }
    Ok(())
}
pub fn loopback_address(host: &str) -> Result<SocketAddr> {
    let address: SocketAddr = host.parse().map_err(|_| "INVALID_DAEMON_ADDRESS")?;
    if address.ip() != IpAddr::V4(std::net::Ipv4Addr::LOCALHOST) || address.port() == 0 {
        return Err("LOOPBACK_ONLY".into());
    }
    Ok(address)
}
fn protected_file(profile: &Path, name: &str) -> Result<Vec<u8>> {
    let path = profile.join(name);
    let meta = fs::symlink_metadata(&path).map_err(|_| "PROFILE_NOT_READY")?;
    if !meta.is_file() || meta.file_type().is_symlink() || meta.len() > 8192 {
        return Err("UNSAFE_PROFILE_FILE".into());
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        if meta.permissions().mode() & 0o077 != 0 {
            return Err("PROFILE_FILE_PERMISSIONS".into());
        }
    }
    let mut bytes = Vec::new();
    fs::File::open(path)
        .map_err(|_| "PROFILE_READ_FAILED")?
        .take(8193)
        .read_to_end(&mut bytes)
        .map_err(|_| "PROFILE_READ_FAILED")?;
    if bytes.len() > 8192 {
        return Err("PROFILE_FILE_LIMIT".into());
    }
    Ok(bytes)
}
impl Control {
    fn connect(&self) -> Result<Connection> {
        let session: Session =
            serde_json::from_slice(&protected_file(&self.profile, "daemon_session.json")?)
                .map_err(|_| "SESSION_INVALID")?;
        valid_id(&session.profile_id, "pro_")?;
        valid_id(&session.workspace_id, "wsp_")?;
        let address = loopback_address(&session.host)?;
        let token = String::from_utf8(protected_file(&self.profile, "owner_cli.token")?)
            .map_err(|_| "TOKEN_INVALID")?
            .trim()
            .to_owned();
        if !token.starts_with("obt_owner_cli_")
            || token.len() > 256
            || !token
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || b == b'_' || b == b'-')
        {
            return Err("TOKEN_INVALID".into());
        }
        Ok(Connection {
            session,
            address,
            token,
        })
    }
    pub fn call(&self, method: &str, path: &str, body: Option<Value>) -> Result<Value> {
        let connection = self.connect()?;
        connection.call(method, path, body)
    }
    pub fn create(&self, goal: &str) -> Result<Value> {
        if goal.trim().is_empty() || goal.chars().count() > 4000 {
            return Err("GOAL_INVALID".into());
        }
        let connection = self.connect()?;
        let settings = connection.call("GET", "/v1/client/settings", None)?;
        connection.call("POST", "/v1/tasks", Some(json!({"goal":goal,"workspace_id":connection.session.workspace_id,"network_mode":settings["config"]["mode"]})))
    }
    pub fn bootstrap_status(&self) -> Result<Value> {
        let profile_exists = self.profile.is_dir();
        let session_ready = self.profile.join("daemon_session.json").is_file()
            && self.profile.join("owner_cli.token").is_file();
        let daemon_alive = self
            .connect()
            .and_then(|c| c.call("GET", "/v1/health", None))
            .is_ok();
        Ok(json!({
            "profile_dir": self.profile.to_string_lossy(),
            "profile_exists": profile_exists,
            "session_ready": session_ready,
            "daemon_alive": daemon_alive,
        }))
    }
}
impl Connection {
    fn call(&self, method: &str, path: &str, body: Option<Value>) -> Result<Value> {
        // Private helper: callers below construct every path. No WebView URL/method is accepted.
        let payload = body
            .map(|b| serde_json::to_vec(&b))
            .transpose()
            .map_err(|_| "BODY_INVALID")?
            .unwrap_or_default();
        if payload.len() > 65536 {
            return Err("BODY_LIMIT".into());
        }
        let mut stream = TcpStream::connect_timeout(&self.address, Duration::from_secs(2))
            .map_err(|_| "DAEMON_UNAVAILABLE")?;
        stream
            .set_read_timeout(Some(Duration::from_secs(5)))
            .map_err(|_| "TRANSPORT_ERROR")?;
        stream
            .set_write_timeout(Some(Duration::from_secs(3)))
            .map_err(|_| "TRANSPORT_ERROR")?;
        let request_id = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map_err(|_| "CLOCK_ERROR")?
            .as_nanos();
        let head = format!("{method} {path} HTTP/1.0\r\nHost: {}\r\nAuthorization: Bearer {}\r\nX-OpenBot-Profile: {}\r\nIdempotency-Key: desktop_{}_{}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n", self.address,self.token,self.session.profile_id,std::process::id(),request_id,payload.len());
        stream
            .write_all(head.as_bytes())
            .and_then(|_| stream.write_all(&payload))
            .map_err(|_| "TRANSPORT_ERROR")?;
        let mut response = Vec::new();
        stream
            .take(1_100_001)
            .read_to_end(&mut response)
            .map_err(|_| "DAEMON_TIMEOUT")?;
        if response.len() > 1_100_000 {
            return Err("RESPONSE_LIMIT".into());
        }
        let split = response
            .windows(4)
            .position(|x| x == b"\r\n\r\n")
            .filter(|n| *n < 16384)
            .ok_or("HTTP_RESPONSE_INVALID")?;
        let headers =
            std::str::from_utf8(&response[..split]).map_err(|_| "HTTP_RESPONSE_INVALID")?;
        let status = headers
            .lines()
            .next()
            .and_then(|line| line.split_whitespace().nth(1))
            .and_then(|s| s.parse::<u16>().ok())
            .ok_or("HTTP_RESPONSE_INVALID")?;
        let value: Value =
            serde_json::from_slice(&response[split + 4..]).map_err(|_| "JSON_RESPONSE_INVALID")?;
        if !(200..300).contains(&status) {
            let code = value["code"].as_str().unwrap_or("SERVER_ERROR");
            return Err(
                if code.len() < 80 && code.bytes().all(|b| b.is_ascii_uppercase() || b == b'_') {
                    code.to_owned()
                } else {
                    "SERVER_ERROR".into()
                },
            );
        }
        Ok(value)
    }
}
#[derive(Deserialize, Serialize, Clone)]
#[serde(deny_unknown_fields)]
pub struct Settings {
    pub locale: String,
    pub model: String,
    pub mode: String,
    pub max_steps: u8,
    pub skill_enabled: bool,
    pub mcp_enabled: bool,
    pub feishu_enabled: bool,
}
impl Settings {
    pub fn validate(&self) -> Result<()> {
        if !["zh-CN", "en"].contains(&self.locale.as_str())
            || !["CONNECTED", "LOCAL_MODEL", "OFFLINE"].contains(&self.mode.as_str())
            || !(1..=8).contains(&self.max_steps)
            || self.model.is_empty()
            || self.model.len() > 96
            || self.model.starts_with("sk-")
            || self.model.contains("://")
            || !self
                .model
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || b"._:/-".contains(&b))
            || (self.mode == "OFFLINE" && self.feishu_enabled)
        {
            return Err("SETTINGS_INVALID".into());
        }
        Ok(())
    }
}
#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Preview {
    pub expected_revision: u64,
    pub config: Settings,
    pub preview_hash: String,
    pub changes: Vec<String>,
    pub activation: String,
    pub confirm: bool,
}
impl Preview {
    pub fn validate(&self) -> Result<()> {
        self.config.validate()?;
        if !self.confirm
            || self.preview_hash.len() != 64
            || !self
                .preview_hash
                .bytes()
                .all(|b| b.is_ascii_hexdigit() && !b.is_ascii_uppercase())
            || !["APPLIED", "NEXT_RUN"].contains(&self.activation.as_str())
            || self.changes.len() > 7
        {
            return Err("PREVIEW_INVALID".into());
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn rejects_routes_and_non_loopback() {
        for id in ["tsk_../secret", "tsk_a\r\nHost:x", "op_test", "tsk_"] {
            assert!(valid_id(id, "tsk_").is_err());
        }
        assert!(valid_id("tsk_abc-123", "tsk_").is_ok());
        for host in [
            "example.com:80",
            "127.0.0.1.evil:1234",
            "192.168.1.2:80",
            "127.0.0.1:0",
        ] {
            assert!(loopback_address(host).is_err());
        }
    }
    #[test]
    fn rejects_unknown_settings_and_keys() {
        let mut value = json!({"locale":"en","model":"demo","mode":"CONNECTED","max_steps":4,"skill_enabled":true,"mcp_enabled":false,"feishu_enabled":false});
        assert!(serde_json::from_value::<Settings>(value.clone())
            .unwrap()
            .validate()
            .is_ok());
        value["api_key"] = json!("synthetic");
        assert!(serde_json::from_value::<Settings>(value.clone()).is_err());
        value.as_object_mut().unwrap().remove("api_key");
        value["model"] = json!("https://unapproved.test");
        assert!(serde_json::from_value::<Settings>(value)
            .unwrap()
            .validate()
            .is_err());
    }
}
