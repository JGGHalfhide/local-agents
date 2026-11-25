Faults passed: 8/8; controls passed: 5/5.

| Case | Kind | Pass | Failed checks | Reported in the case namespace | Ambient findings | Tool calls | Seconds |
|---|---|---|---|---|---|---|---|
| f01 | fault | yes | - | scaled-to-zero Deployment/podinfo | - | 8 | 52.3 |
| f02 | fault | yes | - | image-pull Pod/puller-6979648498-xlxb8 | - | 8 | 42.3 |
| f04 | fault | yes | - | crash-loop Deployment/crashy; crash-loop Pod/crashy-7dfc58bc6d-mcvww | - | 8 | 82.2 |
| f05 | fault | yes | - | oom-killed Pod/hungry-5486775455-gjhzh; oom-killed Deployment/hungry | - | 7 | 77.9 |
| f06 | fault | yes | - | admission-denied Deployment/unsigned | - | 7 | 84.4 |
| f07 | fault | yes | - | unschedulable Pod/greedy-658b9c4b58-f5rsw | - | 8 | 46.1 |
| f08 | fault | yes | - | admission-denied DaemonSet/hostnet | - | 8 | 39.6 |
| f10 | fault | yes | - | storage-unbound PersistentVolumeClaim/data | - | 6 | 46.6 |
| k1 | control | yes | - | - | - | 8 | 54.8 |
| k2 | control | yes | - | - | - | 8 | 50.9 |
| k3 | control | yes | - | - | - | 8 | 48.4 |
| k4 | control | yes | - | - | - | 8 | 48.6 |
| k5 | control | yes | - | - | - | 8 | 48.9 |
