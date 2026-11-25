Faults passed: 8/8; controls passed: 5/5.

| Case | Kind | Pass | Failed checks | Reported in the case namespace | Ambient findings | Tool calls | Seconds |
|---|---|---|---|---|---|---|---|
| f01 | fault | yes | - | scaled-to-zero Deployment/podinfo | admission-denied default/Pod/agent-admission-unsigned; gitops-unhealthy agents/CronJob/status-reporter | 8 | 77.4 |
| f02 | fault | yes | - | image-pull Pod/puller-6979648498-jjj6l; image-pull Deployment/puller | gitops-unhealthy agents/CronJob/status-reporter; admission-denied default/ImageValidatingPolicy/verify-platform-images | 8 | 63.1 |
| f04 | fault | yes | - | crash-loop Pod/crashy-7dfc58bc6d-fp6k9; crash-loop Deployment/crashy | admission-denied default/Pod/agent-admission-unsigned; gitops-unhealthy agents/CronJob/status-reporter | 8 | 76.5 |
| f05 | fault | yes | - | oom-killed Pod/hungry-5486775455-fgxkg | admission-denied default/Pod/agent-admission-unsigned; gitops-unhealthy agents/CronJob/status-reporter | 8 | 64.9 |
| f06 | fault | yes | - | - | admission-denied default/Deployment/agent-eval-f06; admission-denied default/DaemonSet/agent-eval-f08; gitops-unhealthy agents/CronJob/status-reporter | 8 | 75.5 |
| f07 | fault | yes | - | unschedulable Pod/greedy-658b9c4b58-rlfx2; unschedulable Deployment/greedy | image-pull default/ImageValidatingPolicy/verify-platform-images; gitops-unhealthy agents/CronJob/status-reporter | 8 | 92.1 |
| f08 | fault | yes | - | - | admission-denied default/DaemonSet/agent-eval-f08; image-pull default/Deployment/agent-eval-f06; gitops-unhealthy agents/CronJob/status-reporter; other kube-system/DaemonSet/rke2-canal; other kube-system/Job/helm-install-rke2-snapshot-controller | 8 | 127.7 |
| f10 | fault | yes | - | storage-unbound Pod/claimer; storage-unbound PersistentVolumeClaim/data | admission-denied default/ValidatingPolicy/pod-security-restricted; admission-denied default/ImageValidatingPolicy/verify-platform-images | 8 | 68.7 |
| k1 | control | yes | - | - | admission-denied default/DaemonSet/agent-eval-f08; image-pull default/Deployment/agent-eval-f06; gitops-unhealthy agents/CronJob/status-reporter | 8 | 68.1 |
| k2 | control | yes | - | - | crash-loop agents/Job/status-reporter-29926080; admission-denied default/ValidatingPolicy/pod-security-restricted; admission-denied default/ImageValidatingPolicy/verify-platform-images; gitops-unhealthy agents/CronJob/status-reporter | 8 | 72.3 |
| k3 | control | yes | - | - | admission-denied default/ValidatingPolicy/pod-security-restricted; admission-denied default/ImageValidatingPolicy/verify-platform-images; other agents/CronJob/status-reporter | 7 | 82.1 |
| k4 | control | yes | - | - | admission-denied default/DaemonSet/agent-eval-f08; admission-denied default/Deployment/agent-eval-f06; other agents/CronJob/status-reporter | 8 | 56.1 |
| k5 | control | yes | - | - | admission-denied default/DaemonSet/agent-eval-f08; admission-denied default/Deployment/agent-eval-f06; gitops-unhealthy agents/Job/api-smoke-1 | 8 | 61.4 |
