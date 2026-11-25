Faults passed: 8/8; controls passed: 5/5.

| Case | Kind | Pass | Failed checks | Reported in the case namespace | Ambient findings | Tool calls | Seconds |
|---|---|---|---|---|---|---|---|
| f01 | fault | yes | - | scaled-to-zero Deployment/podinfo | - | 8 | 182.3 |
| f02 | fault | yes | - | image-pull Pod/puller-6979648498-vk2ct; image-pull Deployment/puller | - | 8 | 134.1 |
| f04 | fault | yes | - | crash-loop Pod/crashy-7dfc58bc6d-8kfhn | - | 8 | 163.7 |
| f05 | fault | yes | - | oom-killed ReplicaSet/hungry-5486775455 | - | 8 | 170.1 |
| f06 | fault | yes | - | admission-denied Deployment/unsigned | - | 8 | 136.5 |
| f07 | fault | yes | - | unschedulable Pod/greedy-658b9c4b58-cxg58 | - | 7 | 148.3 |
| f08 | fault | yes | - | admission-denied DaemonSet/hostnet | - | 8 | 171.2 |
| f10 | fault | yes | - | unschedulable Pod/claimer; storage-unbound PersistentVolumeClaim/data | - | 8 | 189.6 |
| k1 | control | yes | - | - | - | 8 | 142.8 |
| k2 | control | yes | - | - | - | 8 | 149.8 |
| k3 | control | yes | - | - | - | 8 | 150.8 |
| k4 | control | yes | - | - | - | 8 | 139.8 |
| k5 | control | yes | - | - | - | 8 | 132.1 |
