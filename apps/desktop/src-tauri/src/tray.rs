use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
pub enum TrayState {
    Idle,
    Running,
    WaitingApproval,
    Reconciling,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct TrayPresentation {
    pub state: TrayState,
    pub pending_approvals: usize,
    pub badge_text: String,
    pub tooltip: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct SanitizedNotification {
    pub title: String,
    pub body: String,
    pub contains_raw_secrets: bool,
}

pub fn compute_tray_presentation(
    active_run_state: Option<&str>,
    pending_approvals: usize,
    has_reconciling: bool,
) -> TrayPresentation {
    let state = if has_reconciling || active_run_state == Some("RECONCILING") {
        TrayState::Reconciling
    } else if pending_approvals > 0 || active_run_state == Some("WAITING_APPROVAL") {
        TrayState::WaitingApproval
    } else if active_run_state == Some("RUNNING") {
        TrayState::Running
    } else {
        TrayState::Idle
    };
    let badge_text = if pending_approvals > 0 {
        pending_approvals.to_string()
    } else {
        String::new()
    };
    let tooltip = match state {
        TrayState::Idle => "OpenBot · 空闲 / Idle".to_owned(),
        TrayState::Running => "OpenBot · 执行中 / Running".to_owned(),
        TrayState::WaitingApproval => format!(
            "OpenBot · 待审批 ({pending_approvals}) / Awaiting Approval ({pending_approvals})"
        ),
        TrayState::Reconciling => "OpenBot · 待核对 UNKNOWN / Reconciling".to_owned(),
    };
    TrayPresentation {
        state,
        pending_approvals,
        badge_text,
        tooltip,
    }
}

pub fn build_sanitized_notification(
    kind: &str,
    tool_name: &str,
    data_class: &str,
) -> SanitizedNotification {
    let safe_tool: String = tool_name
        .chars()
        .filter(|c| c.is_ascii_alphanumeric() || *c == '.' || *c == '_' || *c == '-')
        .take(64)
        .collect();
    let body = if data_class == "SECRET" || data_class == "SENSITIVE" {
        format!("工具 {safe_tool} 请求本地审批（敏感详情已隐藏）/ Local review required")
    } else if kind == "RECONCILING" {
        format!("操作 {safe_tool} 结果未知，请在桌面端完成三步核对 / Reconciliation required")
    } else {
        format!("工具 {safe_tool} 等待审批 / Approval requested for {safe_tool}")
    };
    SanitizedNotification {
        title: "OpenBot 安全提醒 / Security Notice".to_owned(),
        body,
        contains_raw_secrets: false,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn tray_and_notifications_never_expose_secrets() {
        let pres = compute_tray_presentation(Some("WAITING_APPROVAL"), 2, false);
        assert_eq!(pres.state, TrayState::WaitingApproval);
        assert_eq!(pres.badge_text, "2");

        let notif =
            build_sanitized_notification("WAITING_APPROVAL", "workspace.apply_patch", "SECRET");
        assert!(!notif.contains_raw_secrets);
        assert!(notif.body.contains("敏感详情已隐藏"));
    }
}
