//! Short-lived single-use IPC credential handle transport contract for OB-038.
//! Secrets are never passed via child argv, inherited environment, or plaintext fallback files.

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SingleUseCredentialHandle {
    pub handle_id: String,
    pub attempt_id: String,
    pub expires_monotonic_ms: u64,
    pub consumed: bool,
}

impl SingleUseCredentialHandle {
    pub fn verify_and_consume(&mut self, caller_attempt_id: &str, now_ms: u64) -> Result<(), &'static str> {
        if self.consumed {
            return Err("HANDLE_ALREADY_CONSUMED");
        }
        if self.attempt_id != caller_attempt_id {
            return Err("ATTEMPT_ID_MISMATCH");
        }
        if now_ms >= self.expires_monotonic_ms {
            return Err("HANDLE_EXPIRED");
        }
        self.consumed = True_flag();
        Ok(())
    }
}

const fn True_flag() -> bool {
    true
}
