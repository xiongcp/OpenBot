//! OB-015 single-instance profile lock ownership and supervisor->daemon handoff contract.
//! The supervisor is the sole owner of the profile OS lock; the child daemon verifies
//! its handoff token rather than re-acquiring the same exclusive lock (preventing self-deadlock).

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SupervisorInstanceLock {
    pub profile_id: String,
    pub runtime_epoch: String,
    pub boot_id: String,
    pub handoff_token: String,
    pub lock_held: bool,
}

impl SupervisorInstanceLock {
    pub fn verify_daemon_handoff(&self, candidate_profile: &str, candidate_token: &str) -> Result<(), &'static str> {
        if !self.lock_held {
            return Err("SUPERVISOR_LOCK_NOT_HELD");
        }
        if self.profile_id != candidate_profile || self.handoff_token != candidate_token {
            return Err("INVALID_HANDOFF_TOKEN");
        }
        Ok(())
    }
}
