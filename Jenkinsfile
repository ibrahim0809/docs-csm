@Library("dst-shared@main") _
rpmBuild (
    githubPushRepo : "Cray-HPE/docs-csm-install",
    githubPushBranches : "(release/.*|main)",
    specfile : "docs-csm-install.spec",
    product : "csm",
    target_node : "ncn",
    fanout_params: ["sle15sp2"],
    channel : "metal-ci-alerts",
    slack_notify : ['', 'SUCCESS', 'FAILURE', 'FIXED']
)
