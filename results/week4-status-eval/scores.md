Faults passed: 8/8; controls passed: 5/5.

| Case | Kind | Pass | Failed checks | Reported in the case namespace | Ambient findings | Tool calls | Seconds |
|---|---|---|---|---|---|---|---|
| f01 | fault | yes | - | scaled-to-zero Deployment/podinfo | - | 8 | 47.3 |
| f02 | fault | yes | - | image-pull Pod/puller-6979648498-8k9r6; image-pull Deployment/puller; image-pull ReplicaSet/puller-6979648498 | - | 8 | 54.7 |
| f04 | fault | yes | - | crash-loop Pod/crashy-7dfc58bc6d-rwcx8 | - | 8 | 52.6 |
| f05 | fault | yes | - | oom-killed Pod/hungry-5486775455-xjglw | - | 8 | 93.2 |
| f06 | fault | yes | - | admission-denied Deployment/unsigned | - | 7 | 84.7 |
| f07 | fault | yes | - | unschedulable Pod/greedy-658b9c4b58-5blxl | - | 8 | 47.6 |
| f08 | fault | yes | - | admission-denied DaemonSet/hostnet | - | 8 | 78.3 |
| f10 | fault | yes | - | storage-unbound PersistentVolumeClaim/data | - | 6 | 49.2 |
| k1 | control | yes | - | - | - | 8 | 55.0 |
| k2 | control | yes | - | - | - | 8 | 48.6 |
| k3 | control | yes | - | - | - | 8 | 49.4 |
| k4 | control | yes | - | - | - | 8 | 48.9 |
| k5 | control | yes | - | - | - | 8 | 49.4 |
