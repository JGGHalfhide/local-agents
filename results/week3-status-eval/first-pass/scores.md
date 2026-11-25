Faults passed: 7/8; controls passed: 5/5.

| Case | Kind | Pass | Failed checks | Reported in the case namespace | Ambient findings | Tool calls | Seconds |
|---|---|---|---|---|---|---|---|
| f01 | fault | yes | - | scaled-to-zero Deployment/podinfo | admission-denied agents/Job/status-reporter-29926080; admission-denied agents/CronJob/status-reporter | 7 | 108.1 |
| f02 | fault | yes | - | image-pull Pod/puller-6979648498-85585; image-pull Deployment/puller | admission-denied agents/CronJob/status-reporter; crash-loop agents/Job/status-reporter-29926080; other agents/CronJob/status-reporter | 8 | 112.3 |
| f04 | fault | yes | - | crash-loop Pod/crashy-7dfc58bc6d-gm97b; crash-loop Deployment/crashy | crash-loop agents/Job/status-reporter-29926080; admission-denied agents/CronJob/status-reporter | 8 | 88.0 |
| f05 | fault | yes | - | oom-killed Pod/hungry-5486775455-8g8nc; crash-loop Deployment/hungry | crash-loop agents/Job/status-reporter-29926080; crash-loop agents/Job/status-reporter-29926080-tccdf; admission-denied agents/CronJob/status-reporter | 8 | 94.6 |
| f06 | fault | NO | classify | image-pull Deployment/unsigned | crash-loop agents/Job/status-reporter-29926080; admission-denied agents/CronJob/status-reporter | 8 | 109.8 |
| f07 | fault | yes | - | unschedulable Pod/greedy-658b9c4b58-m8gp6; unschedulable Deployment/greedy | crash-loop agents/Job/status-reporter-29926080; admission-denied agents/CronJob/status-reporter | 8 | 72.7 |
| f08 | fault | yes | - | admission-denied DaemonSet/hostnet | crash-loop agents/Job/status-reporter-29926080; admission-denied agents/CronJob/status-reporter | 8 | 93.7 |
| f10 | fault | yes | - | storage-unbound PersistentVolumeClaim/data; unschedulable Pod/claimer | admission-denied agents/CronJob/status-reporter; crash-loop agents/Job/status-reporter-29926080; gitops-unhealthy agents/CronJob/status-reporter | 8 | 83.8 |
| k1 | control | yes | - | - | admission-denied agents/CronJob/status-reporter | 5 | 60.5 |
| k2 | control | yes | - | - | admission-denied agents/CronJob/status-reporter; scaled-to-zero agents/Job/status-reporter-29926080; unschedulable agents/Pod/status-reporter-29926080-tccdf; other agents/CronJob/status-reporter | 5 | 149.3 |
| k3 | control | yes | - | - | crash-loop agents/Job/status-reporter-29926080 | 5 | 51.2 |
| k4 | control | yes | - | - | admission-denied agents/CronJob/status-reporter | 5 | 60.4 |
| k5 | control | yes | - | - | admission-denied agents/CronJob/status-reporter | 5 | 61.8 |
