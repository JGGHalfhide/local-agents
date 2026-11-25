Faults passed: 8/8; controls passed: 5/5.

| Case | Kind | Pass | Failed checks | Reported in the case namespace | Ambient findings | Tool calls | Seconds |
|---|---|---|---|---|---|---|---|
| f01 | fault | yes | - | scaled-to-zero Deployment/podinfo | - | 8 | 48.1 |
| f02 | fault | yes | - | image-pull Pod/puller-6979648498-925gl | - | 8 | 43.4 |
| f04 | fault | yes | - | crash-loop Deployment/crashy | - | 8 | 55.5 |
| f05 | fault | yes | - | oom-killed Pod/hungry-5486775455-bdqb5; crash-loop Deployment/hungry; crash-loop ReplicaSet/hungry-5486775455 | - | 8 | 81.7 |
| f06 | fault | yes | - | admission-denied Deployment/unsigned | - | 8 | 62.4 |
| f07 | fault | yes | - | unschedulable Pod/greedy-658b9c4b58-6k7mj | - | 8 | 43.6 |
| f08 | fault | yes | - | admission-denied DaemonSet/hostnet | - | 8 | 89.4 |
| f10 | fault | yes | - | storage-unbound PersistentVolumeClaim/data | - | 5 | 61.6 |
| k1 | control | yes | - | - | - | 8 | 47.3 |
| k2 | control | yes | - | - | - | 8 | 46.2 |
| k3 | control | yes | - | - | - | 8 | 47.3 |
| k4 | control | yes | - | - | - | 8 | 47.6 |
| k5 | control | yes | - | - | - | 8 | 47.7 |
