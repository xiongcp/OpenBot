//! OB-042 process-tree supervision and platform boundary contract.
//! - Windows: CreateProcessW(CREATE_SUSPENDED) -> AssignProcessToJobObject -> ResumeThread.
//! - Linux: cgroup v2 or process group + PR_SET_PDEATHSIG.
//! - macOS: process group (setpgid/killpg) + container ID tracking.
//! Drop and pipe EOF are cooperative hints only and never prove 100% forced cleanup.

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SupervisedWorkerTree {
    pub worker_id: String,
    pub runtime_epoch: String,
    pub pid: u32,
    pub pgid: u32,
    pub start_token: String,
    pub container_id: Option<String>,
    pub confirmed_isolated: bool,
}

impl SupervisedWorkerTree {
    pub fn can_allow_new_dispatch(&self) -> bool {
        self.confirmed_isolated
    }
}
