Faults passed: 6/6; controls passed: 3/4.

| Case | Kind | Pass | Failed checks | Reported in the case namespace | Ambient findings | Tool calls | Seconds |
|---|---|---|---|---|---|---|---|
| f01 | fault | yes | - | scaled-to-zero Deployment/podinfo | admission-denied default/Pod/agent-admission-unsigned; gitops-unhealthy agents/CronJob/status-reporter | 8 | 77.4 |
| f02 | fault | yes | - | image-pull Pod/puller-6979648498-jjj6l; image-pull Deployment/puller | gitops-unhealthy agents/CronJob/status-reporter; admission-denied default/ImageValidatingPolicy/verify-platform-images | 8 | 63.1 |
| f04 | fault | yes | - | crash-loop Pod/crashy-7dfc58bc6d-fp6k9; crash-loop Deployment/crashy | admission-denied default/Pod/agent-admission-unsigned; gitops-unhealthy agents/CronJob/status-reporter | 8 | 76.5 |
| f05 | fault | yes | - | oom-killed Pod/hungry-5486775455-fgxkg | admission-denied default/Pod/agent-admission-unsigned; gitops-unhealthy agents/CronJob/status-reporter | 8 | 64.9 |
| f07 | fault | yes | - | unschedulable Pod/greedy-658b9c4b58-rlfx2; unschedulable Deployment/greedy | image-pull default/ImageValidatingPolicy/verify-platform-images; gitops-unhealthy agents/CronJob/status-reporter | 8 | 92.1 |
| f10 | fault | yes | - | storage-unbound Pod/claimer; storage-unbound PersistentVolumeClaim/data | admission-denied default/ValidatingPolicy/pod-security-restricted; admission-denied default/ImageValidatingPolicy/verify-platform-images | 8 | 68.7 |
| k2 | control | NO | tool_validity | - | admission-denied default/DaemonSet/agent-eval-f08; image-pull default/Deployment/agent-eval-f06; other agents/CronJob/status-reporter | 8 | 69.9 |
| k3 | control | yes | - | - | admission-denied default/ValidatingPolicy/pod-security-restricted; admission-denied default/ImageValidatingPolicy/verify-platform-images; other agents/CronJob/status-reporter | 7 | 82.1 |
| k4 | control | yes | - | - | admission-denied default/DaemonSet/agent-eval-f08; admission-denied default/Deployment/agent-eval-f06; other agents/CronJob/status-reporter | 8 | 56.1 |
| k5 | control | yes | - | - | admission-denied default/DaemonSet/agent-eval-f08; admission-denied default/Deployment/agent-eval-f06; gitops-unhealthy agents/Job/api-smoke-1 | 8 | 61.4 |
