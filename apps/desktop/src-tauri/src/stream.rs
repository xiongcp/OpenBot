use serde::{Deserialize, Serialize};
use serde_json::Value;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct SseFrame {
    pub last_event_id: Option<u64>,
    pub event_type: String,
    pub data: Value,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum StreamPollAction {
    Events(Vec<SseFrame>),
    CursorExpiredReloadSnapshot,
}

pub fn build_keep_alive_sse_request(
    host: &str,
    profile_id: &str,
    token: &str,
    task_id: &str,
    last_event_id: u64,
) -> Result<String, String> {
    if !task_id.starts_with("tsk_") {
        return Err("INVALID_ID".into());
    }
    Ok(format!(
        "GET /v1/tasks/{task_id}/events?after_seq={last_event_id} HTTP/1.1\r\nHost: {host}\r\nAuthorization: Bearer {token}\r\nX-OpenBot-Profile: {profile_id}\r\nAccept: text/event-stream\r\nLast-Event-ID: {last_event_id}\r\nConnection: keep-alive\r\n\r\n"
    ))
}

pub fn parse_sse_response(status: u16, raw_body: &str) -> Result<StreamPollAction, String> {
    if status == 410 {
        return Ok(StreamPollAction::CursorExpiredReloadSnapshot);
    }
    if !(200..300).contains(&status) {
        return Err("SSE_STREAM_HTTP_ERROR".into());
    }
    let mut frames = Vec::new();
    for block in raw_body.replace("\r\n", "\n").split("\n\n") {
        let trimmed = block.trim();
        if trimmed.is_empty() {
            continue;
        }
        let mut last_id: Option<u64> = None;
        let mut ev_type = String::from("message");
        let mut data_lines = Vec::new();
        for line in trimmed.lines() {
            if let Some(rest) = line.strip_prefix("id:") {
                last_id = rest.trim().parse::<u64>().ok();
            } else if let Some(rest) = line.strip_prefix("event:") {
                ev_type = rest.trim().to_owned();
            } else if let Some(rest) = line.strip_prefix("data:") {
                data_lines.push(rest.trim());
            }
        }
        if !data_lines.is_empty() {
            let joined = data_lines.join("\n");
            let parsed: Value = serde_json::from_str(&joined).map_err(|_| "SSE_JSON_INVALID")?;
            frames.push(SseFrame {
                last_event_id: last_id,
                event_type: ev_type,
                data: parsed,
            });
        }
    }
    Ok(StreamPollAction::Events(frames))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_sse_frames_and_handles_410_cursor_expiry() {
        let req = build_keep_alive_sse_request(
            "127.0.0.1:41931",
            "pro_test1",
            "obt_owner_cli_123",
            "tsk_1",
            7,
        )
        .unwrap();
        assert!(req.contains("HTTP/1.1"));
        assert!(req.contains("Connection: keep-alive"));
        assert!(req.contains("Last-Event-ID: 7"));

        let expired = parse_sse_response(410, "{\"code\":\"EVENT_CURSOR_EXPIRED\"}").unwrap();
        assert_eq!(expired, StreamPollAction::CursorExpiredReloadSnapshot);

        let body = "id: 8\nevent: TOOL_PROPOSED\ndata: {\"event_id\":\"evt_8\"}\n\n";
        let ok = parse_sse_response(200, body).unwrap();
        match ok {
            StreamPollAction::Events(items) => {
                assert_eq!(items.len(), 1);
                assert_eq!(items[0].last_event_id, Some(8));
                assert_eq!(items[0].event_type, "TOOL_PROPOSED");
            }
            _ => panic!("expected events"),
        }
    }
}
