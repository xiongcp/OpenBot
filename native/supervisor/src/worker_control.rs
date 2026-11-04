//! OB-041 container sandbox worker lifecycle guard.
//! Enforces stop -> wait -> export_verified -> remove ordering and refuses to touch
//! unregistered containers or assume client PID exit implies container termination.

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RegisteredContainer {
    pub container_id: String,
    pub profile_id: String,
    pub operation_id: String,
    pub attempt_id: String,
    pub runtime_epoch: String,
    pub stopped_and_waited: bool,
    pub export_validated: bool,
    pub removed: bool,
}

impl RegisteredContainer {
    pub fn mark_stopped_and_waited(&mut self) {
        self.stopped_and_waited = true;
    }

    pub fn can_export(&self) -> bool {
        self.stopped_and_waited && !self.removed
    }

    pub fn can_remove(&self) -> bool {
        self.stopped_and_waited && self.export_validated && !self.removed
    }
}
