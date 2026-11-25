Faults passed: 8/8; controls passed: 5/5.

| Case | Kind | Pass | Failed checks | Reported in the case namespace | Ambient findings | Tool calls | Seconds |
|---|---|---|---|---|---|---|---|
| f01 | fault | yes | - | scaled-to-zero Deployment/podinfo | - | 6 | 97.7 |
| f02 | fault | yes | - | image-pull Pod/puller-6979648498-gnxr6 | - | 6 | 51.7 |
| f04 | fault | yes | - | crash-loop Deployment/crashy | - | 6 | 59.6 |
| f05 | fault | yes | - | oom-killed Pod/hungry-5486775455-trj9r; crash-loop Deployment/hungry | - | 8 | 64.8 |
| f06 | fault | yes | - | admission-denied Deployment/unsigned | admission-denied kube-system/Addon/local-path-storage | 8 | 104.1 |
| f07 | fault | yes | - | unschedulable Pod/greedy-658b9c4b58-7ctb6 | - | 6 | 47.0 |
| f08 | fault | yes | - | admission-denied DaemonSet/hostnet | other kube-system/Addon/local-path-storage | 8 | 94.8 |
| f10 | fault | yes | - | storage-unbound Pod/claimer; storage-unbound PersistentVolumeClaim/data | - | 6 | 71.8 |
| k1 | control | yes | - | - | other kube-system/Addon/local-path-storage | 7 | 67.7 |
| k2 | control | yes | - | - | other kube-system/Addon/local-path-storage | 7 | 72.0 |
| k3 | control | yes | - | - | other kube-system/Addon/local-path-storage | 7 | 66.2 |
| k4 | control | yes | - | - | other kube-system/Addon/local-path-storage | 7 | 71.0 |
| k5 | control | yes | - | - | other kube-system/Addon/local-path-storage | 7 | 106.7 |
