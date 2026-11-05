mod control;
pub mod stream;
pub mod tray;
use control::{valid_id, Control, Preview, Settings};
use serde_json::{json, Value};
use std::path::PathBuf;
use tauri::State;

type Result<T> = std::result::Result<T, String>;
fn snapshot(control: &Control) -> Result<Value> {
    Ok(json!({
        "settings":control.call("GET","/v1/client/settings",None)?,
        "runs":control.call("GET","/v1/client/runs",None)?,
        "approvals":control.call("GET","/v1/client/approvals",None)?,
        "health":control.call("GET","/v1/client/health",None)?,
        "feishu":control.call("GET","/v1/client/feishu",None)?,
    }))
}
#[tauri::command]
async fn client_snapshot(control: State<'_, Control>) -> Result<Value> {
    snapshot(&control)
}
#[tauri::command]
async fn client_reconnect(control: State<'_, Control>) -> Result<Value> {
    snapshot(&control)
}
#[tauri::command]
async fn client_trace(
    control: State<'_, Control>,
    task_id: String,
    after_seq: u64,
) -> Result<Value> {
    valid_id(&task_id, "tsk_")?;
    if after_seq > 999_999_999_999_999_999 {
        return Err("CURSOR_INVALID".into());
    }
    control.call(
        "GET",
        &format!("/v1/client/tasks/{task_id}/trace?after_seq={after_seq}"),
        None,
    )
}
#[tauri::command]
async fn client_create(control: State<'_, Control>, goal: String) -> Result<Value> {
    control.create(&goal)
}
#[tauri::command]
async fn client_start(control: State<'_, Control>, task_id: String) -> Result<Value> {
    valid_id(&task_id, "tsk_")?;
    control.call(
        "POST",
        &format!("/v1/client/tasks/{task_id}/start"),
        Some(json!({})),
    )
}
#[tauri::command]
async fn client_confirm_pair(control: State<'_, Control>, candidate_id: String) -> Result<Value> {
    valid_id(&candidate_id, "pcn_")?;
    control.call(
        "POST",
        "/v1/client/feishu/confirm",
        Some(json!({"candidate_id":candidate_id,"confirm":true})),
    )
}
#[tauri::command]
async fn client_cancel(
    control: State<'_, Control>,
    task_id: String,
    expected_version: u64,
) -> Result<Value> {
    valid_id(&task_id, "tsk_")?;
    control.call(
        "POST",
        &format!("/v1/tasks/{task_id}/cancel"),
        Some(json!({"expected_version":expected_version})),
    )
}
#[tauri::command]
async fn client_preview_settings(
    control: State<'_, Control>,
    expected_revision: u64,
    config: Settings,
) -> Result<Value> {
    config.validate()?;
    control.call(
        "POST",
        "/v1/client/settings/preview",
        Some(json!({"expected_revision":expected_revision,"config":config})),
    )
}
#[tauri::command]
async fn client_apply_settings(control: State<'_, Control>, preview: Preview) -> Result<Value> {
    preview.validate()?;
    control.call(
        "POST",
        "/v1/client/settings/apply",
        Some(serde_json::to_value(preview).map_err(|_| "PREVIEW_INVALID")?),
    )
}
#[tauri::command]
async fn client_decide(
    control: State<'_, Control>,
    approval_id: String,
    decision: String,
    expected_version: u64,
    binding_hash: String,
) -> Result<Value> {
    valid_id(&approval_id, "apr_")?;
    if !["APPROVE", "DENY"].contains(&decision.as_str())
        || expected_version == 0
        || binding_hash.len() != 71
        || !binding_hash.starts_with("sha256:")
        || !binding_hash[7..]
            .bytes()
            .all(|b| b.is_ascii_hexdigit() && !b.is_ascii_uppercase())
    {
        return Err("DECISION_INVALID".into());
    }
    let current = control.call("GET", &format!("/v1/approvals/{approval_id}/preview"), None)?;
    if current["binding_hash"] != binding_hash || current["version"] != expected_version {
        return Err("CONFLICT".into());
    }
    let challenge = control.call(
        "POST",
        &format!("/v1/approvals/{approval_id}/challenge"),
        None,
    )?;
    let nonce = challenge["nonce"].as_str().ok_or("CHALLENGE_UNAVAILABLE")?;
    control.call("POST",&format!("/v1/approvals/{approval_id}/decide"),Some(json!({"decision":decision,"expected_version":expected_version,"expected_binding_hash":binding_hash,"nonce":nonce})))
}
#[tauri::command]
async fn client_bootstrap_status(control: State<'_, Control>) -> Result<Value> {
    control.bootstrap_status()
}
#[tauri::command]
async fn client_submit_evidence(
    control: State<'_, Control>,
    operation_id: String,
    content: String,
) -> Result<Value> {
    valid_id(&operation_id, "op_")?;
    if content.trim().is_empty() || content.len() > 16384 {
        return Err("EVIDENCE_INVALID".into());
    }
    control.call(
        "POST",
        &format!("/v1/operations/{operation_id}/evidence"),
        Some(json!({"content": content, "mime": "text/plain"})),
    )
}
#[tauri::command]
async fn client_reconcile_operation(
    control: State<'_, Control>,
    operation_id: String,
    expected_version: u64,
    outcome: String,
    evidence_artifact_ids: Vec<String>,
) -> Result<Value> {
    valid_id(&operation_id, "op_")?;
    if ![
        "CONFIRMED_SUCCEEDED",
        "CONFIRMED_NOT_EXECUTED",
        "KEEP_UNKNOWN",
    ]
    .contains(&outcome.as_str())
        || expected_version == 0
        || evidence_artifact_ids.len() > 8
    {
        return Err("RECONCILE_INVALID".into());
    }
    for aid in &evidence_artifact_ids {
        valid_id(aid, "art_")?;
    }
    control.call(
        "POST",
        &format!("/v1/operations/{operation_id}/reconcile"),
        Some(json!({
            "expected_version": expected_version,
            "outcome": outcome,
            "evidence_artifact_ids": evidence_artifact_ids,
        })),
    )
}
#[tauri::command]
async fn client_emergency_stop(control: State<'_, Control>) -> Result<Value> {
    let runs = control.call("GET", "/v1/client/runs", None)?;
    let mut cancelled = Vec::new();
    if let Some(arr) = runs["runs"].as_array() {
        for item in arr {
            let st = item["state"].as_str().unwrap_or("");
            if ["RUNNING", "QUEUED", "WAITING_APPROVAL", "PAUSED"].contains(&st) {
                if let (Some(tid), Some(ver)) =
                    (item["task_id"].as_str(), item["version"].as_u64())
                {
                    if control
                        .call(
                            "POST",
                            &format!("/v1/tasks/{tid}/cancel"),
                            Some(json!({"expected_version": ver})),
                        )
                        .is_ok()
                    {
                        cancelled.push(tid.to_owned());
                    }
                }
            }
        }
    }
    Ok(json!({"emergency_stopped_tasks": cancelled}))
}
pub fn run() {
    let args: Vec<_> = std::env::args_os().collect();
    let profile = if args.len() == 3 && args[1] == "--profile-dir" {
        PathBuf::from(&args[2])
    } else {
        std::env::var_os("OPENBOT_PROFILE_DIR")
            .map(PathBuf::from)
            .unwrap_or_else(|| {
                PathBuf::from(std::env::var_os("HOME").unwrap_or_default()).join(".openbot/default")
            })
    };
    tauri::Builder::default()
        .manage(Control { profile })
        .invoke_handler(tauri::generate_handler![
            client_snapshot,
            client_trace,
            client_create,
            client_start,
            client_confirm_pair,
            client_cancel,
            client_preview_settings,
            client_apply_settings,
            client_decide,
            client_reconnect,
            client_bootstrap_status,
            client_submit_evidence,
            client_reconcile_operation,
            client_emergency_stop
        ])
        .setup(|app| {
            tauri::WebviewWindowBuilder::new(
                app,
                "main",
                tauri::WebviewUrl::App("index.html".into()),
            )
            .title("OpenBot")
            .inner_size(1360.0, 900.0)
            .min_inner_size(1100.0, 720.0)
            .on_navigation(|url| {
                url.scheme() == "tauri"
                    || (url.scheme() == "http" && url.host_str() == Some("tauri.localhost"))
            })
            .build()?;
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("OpenBot client could not start");
}
