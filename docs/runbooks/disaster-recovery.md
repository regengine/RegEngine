# Disaster Recovery Runbook — moved

The disaster-recovery procedure is now a single document:
[docs/operations/DISASTER_RECOVERY.md](../operations/DISASTER_RECOVERY.md).

This file used to describe docker-compose services with S3 uploads, which is
not how production runs. Production runs on Railway. The old text remains in
git history (`git log -p -- docs/runbooks/disaster-recovery.md`).
