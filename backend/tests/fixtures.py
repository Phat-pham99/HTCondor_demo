from __future__ import annotations

from datetime import datetime, timezone

BASE = int(datetime(2026, 10, 13, 10, 20, 15, tzinfo=timezone.utc).timestamp())

SUCCESS_LOG = """\
000 (012.000.000) 2026-10-13 10:20:15 Job submitted from host: <172.18.0.2:1119?addrs=172.18.0.2-1119&alias=condor-manager&noUDP&sock=schedd_1_2>
...
040 (012.000.000) 2026-10-13 10:20:22 Started transferring input files
\tTransferring to host: <172.18.0.5:9702?addrs=172.18.0.5-9702&alias=condor-worker-1-0&noUDP&sock=startd_1_2>
...
040 (012.000.000) 2026-10-13 10:20:22 Finished transferring input files
...
001 (012.000.000) 2026-10-13 10:20:24 Job executing on host: <172.18.0.5:9702?addrs=172.18.0.5-9702&alias=condor-worker-1-0&noUDP&sock=startd_1_2>
\tSlotName: slot1@condor-worker-1-0
\tCondorScratchDir = "/var/lib/condor/execute/dir_42"
...
006 (012.000.000) 2026-10-13 10:20:29 Image size of job updated: 2500
\t3  -  MemoryUsage of job (MB)
...
040 (012.000.000) 2026-10-13 10:22:07 Started transferring output files
...
040 (012.000.000) 2026-10-13 10:22:08 Finished transferring output files
...
005 (012.000.000) 2026-10-13 10:22:08 Job terminated.
\t(1) Normal termination (return value 0)
\t\tUsr 0 00:00:01, Sys 0 00:00:00  -  Run Remote Usage
...
"""

FAILED_LOG = """\
000 (013.000.000) 2026-10-13T10:30:00 Job submitted from host: <172.18.0.2:1119?alias=condor-manager>
...
001 (013.000.000) 2026-10-13T10:30:05 Job executing on host: <172.18.0.6:9702?alias=condor-worker-2-0>
...
005 (013.000.000) 2026-10-13T10:30:06 Job terminated.
\t(1) Normal termination (return value 1)
...
012 (014.000.000) 2026-10-13T10:31:00 Job was held.
\tTransfer output files failure at execution point slot1@condor-worker-2-0 while sending files to access point condor-manager.
\tCode 12 Subcode 2
...
"""


def job_ad(cluster: int = 12, proc: int = 0, **overrides):
    ad = {
        "ClusterId": cluster,
        "ProcId": proc,
        "GlobalJobId": f"condor-manager#{cluster}.{proc}#{BASE}",
        "Owner": "demo",
        "JobStatus": 4,
        "QDate": BASE,
        "LastMatchTime": BASE + 7,
        "JobStartDate": BASE + 9,
        "JobCurrentStartDate": BASE + 9,
        "CompletionDate": BASE + 113,
        "EnteredCurrentStatus": BASE + 113,
        "LastRemoteHost": "slot1@condor-worker-1-0",
        "ExitCode": 0,
        "ExitBySignal": False,
        "Cmd": "/workload_demo/monte_carlo_pi.py",
        "Iwd": "/workload_demo",
        "OutputDirectory": "/out",
        "TransferOutput": f"pi-{cluster}-{proc}.json",
        "Out": f"/out/pi-{cluster}-{proc}.log",
        "Err": f"/out/pi-{cluster}-{proc}.err",
        "NumJobStarts": 1,
    }
    ad.update(overrides)
    return {key: value for key, value in ad.items() if value is not None}


def slot_ad(name: str, state: str = "Unclaimed", activity: str = "Idle", **overrides):
    ad = {
        "Name": name,
        "Machine": name.split("@", 1)[1],
        "State": state,
        "Activity": activity,
        "SlotType": "Static",
        "Cpus": 1,
        "Memory": 512,
        "TotalCpus": 1,
        "TotalMemory": 512,
        "LastHeardFrom": BASE + 100,
    }
    ad.update(overrides)
    return ad
