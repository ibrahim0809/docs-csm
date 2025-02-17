

# Utility Storage

Utility storage is designed to support Kubernetes and the System Management Services (SMS) it orchestrates. Utility storage is a cost-effective solution for storing the large amounts of telemetry and log data collected.

Ceph is the utility storage platform that is used to enable pods to store persistent data. It is deployed to provide block, object, and file storage to the management services running on Kubernetes, as well as for telemetry data coming from the compute nodes.

**IMPORTANT NOTES:**

- Commands for Ceph health must be run from either ncn-m or ncn-s001/2/3 unless they are otherwise specified to run on the host in question.
- ncn-m and ncn-s001/2/3 are the only servers with the credentials. Individual procedures will specify when to run a command from a node other than those.


## Key Concepts

> - **Shrink:** This only pertains to removing nodes from a cluster.  Since Octopus and the move to utilize ceph orchestrator, the ceph     cluster is probing nodes and adding unused drives.  So removing a drive will only work if the actual drive is removed from aserver.
> - **Add:** This will most commonly pertain to adding a node with its full allotment of drives.  
> - **Replace:** This will most commonly pertain to replacing a drive or a node after hardware repairs.

