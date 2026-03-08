## 📦 **পর্ব ১৮: ডেভঅপস ও সাইট রিলায়েবিলিটি ইঞ্জিনিয়ারিং (SRE)**

### **18. sre/runbooks/service-down.md** - সার্ভিস ডাউন রানবুক
```markdown
# 🚨 Service Down Runbook

## 📋 Quick Reference

| Metadata | Value |
|----------|-------|
| **Alert Name** | ServiceDown |
| **Severity** | Critical (P0) |
| **SLA Target** | 99.99% uptime |
| **MTTR Target** | < 15 minutes |
| **Escalation** | Platform Team → Engineering Manager → VP Engineering |
| **Document Owner** | SRE Team |

## 🎯 Description

This alert fires when a critical service becomes unavailable or unresponsive. This could be due to application crashes, infrastructure failures, network issues, or resource exhaustion.

## 🔍 Initial Investigation

### 1. Check Service Status
```bash
# Check if service is running
systemctl status trading-backend
docker ps | grep trading-backend
kubectl get pods -n production | grep backend

# Check recent logs
journalctl -u trading-backend -n 100 --no-pager
kubectl logs -n production deployment/backend --tail=100
```

### 2. Check Resource Usage
```bash
# CPU/Memory usage
top -c -u trading
htop
kubectl top pods -n production

# Disk space
df -h
du -sh /var/log/trading/

# Network connections
netstat -tulpn | grep :8000
ss -tulpn | grep :8000
```

### 3. Check Dependencies
```bash
# Database connectivity
psql -h postgres-primary -U trading_user -d trading_prod -c "SELECT 1;"

# Redis connectivity
redis-cli -h redis-master ping

# RabbitMQ connectivity
rabbitmqctl ping
```

## 🛠️ Recovery Steps

### Option A: Restart Service
```bash
# Systemd
sudo systemctl restart trading-backend

# Docker
docker restart trading-backend

# Kubernetes
kubectl rollout restart deployment/backend -n production
```

### Option B: Scale Up
```bash
# Increase replicas
kubectl scale deployment/backend --replicas=5 -n production

# Check if nodes have capacity
kubectl describe nodes
kubectl describe pod -n production | grep -A5 "Events:"
```

### Option C: Failover
```bash
# Switch to standby
kubectl patch service backend -n production -p '{"spec":{"selector":{"version":"standby"}}}'

# Promote replica
kubectl scale deployment/backend-standby --replicas=3 -n production
```

### Option D: Rollback
```bash
# Rollback to previous version
kubectl rollout undo deployment/backend -n production

# Check rollout status
kubectl rollout status deployment/backend -n production
```

## 📊 Verification

After recovery, verify service health:

```bash
# Health check
curl -f https://api.tradingecosystem.com/health

# Check metrics
curl localhost:9090/metrics | grep backend_up

# Test functionality
python3 scripts/smoke_test.py
```

## 🔍 Root Cause Analysis

### Common Causes & Solutions

| Cause | Probability | Solution |
|-------|------------|----------|
| **Out of Memory** | 35% | Increase memory limits, optimize code |
| **Database Connection Pool Exhausted** | 25% | Increase pool size, check for connection leaks |
| **Deadlock/Crash** | 20% | Fix bug, add retry logic, improve error handling |
| **Network Partition** | 10% | Check network policies, DNS, firewall |
| **Disk Full** | 5% | Clean logs, increase disk size |
| **External API Down** | 5% | Implement circuit breaker, fallback |

### Diagnostic Commands

```bash
# Check OOM killer
sudo journalctl -k | grep -i "Out of memory"

# Check database connections
SELECT count(*) FROM pg_stat_activity;

# Check slow queries
SELECT query, calls, total_time FROM pg_stat_statements ORDER BY total_time DESC LIMIT 10;

# Check stack trace
gdb -p $(pgrep trading-backend) -batch -ex "thread apply all bt"
```

## 📈 Post-Incident Actions

### Immediate (24h)
- [ ] Write detailed incident report
- [ ] Add monitoring for root cause
- [ ] Update runbook with findings
- [ ] Communicate with stakeholders

### Short-term (1 week)
- [ ] Implement automated recovery
- [ ] Add chaos engineering tests
- [ ] Review and improve SLIs/SLOs
- [ ] Schedule post-mortem meeting

### Long-term (1 month)
- [ ] Architecture review
- [ ] Capacity planning update
- [ ] Disaster recovery test
- [ ] Update training materials

## 📝 Incident Report Template

```markdown
## Incident Report: Service Down

**Incident ID:** INC-{{date}}-{{sequence}}
**Date:** {{date}}
**Duration:** {{duration}}
**Severity:** P0
**Affected Services:** {{services}}

### Timeline
- {{time}} - Alert triggered
- {{time}} - Investigation started
- {{time}} - Root cause identified
- {{time}} - Recovery initiated
- {{time}} - Service restored
- {{time}} - Monitoring confirmed

### Root Cause
{{root_cause}}

### Impact
- {{metric}} affected
- {{users}} impacted
- {{loss}} estimated loss

### Actions Taken
1. {{action}}
2. {{action}}
3. {{action}}

### Prevention
- [ ] {{prevention_item}}
- [ ] {{prevention_item}}

### Lessons Learned
- {{lesson}}
- {{lesson}}
```

## 📊 Metrics & Dashboards

### Key Metrics to Monitor
- **Uptime**: `avg_over_time(up{job="backend"}[1h])`
- **Error Rate**: `sum(rate(http_requests_total{status=~"5.."}[5m]))`
- **Latency**: `histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))`
- **CPU**: `sum(rate(container_cpu_usage_seconds_total[5m])) by (pod)`
- **Memory**: `sum(container_memory_usage_bytes) by (pod)`

### Dashboards
- [Grafana - Service Health](https://grafana.{{domain}}/d/service-health)
- [Grafana - Resource Usage](https://grafana.{{domain}}/d/resource-usage)
- [Kibana - Error Logs](https://kibana.{{domain}}/app/discover#/view/errors)

## 📞 Escalation Contacts

| Role | Name | Phone | Slack | Email |
|------|------|-------|-------|-------|
| Primary On-call | @oncall | +1-555-0123 | @sre-oncall | oncall@company.com |
| Secondary On-call | @sre2 | +1-555-0124 | @sre-backup | sre-backup@company.com |
| Engineering Manager | @em | +1-555-0125 | @engineering-mgr | eng-mgr@company.com |
| VP Engineering | @vpe | +1-555-0126 | @vp-engineering | vp-eng@company.com |

## 🔄 Related Runbooks
- [Database Failure](database-failure.md)
- [High Latency](high-latency.md)
- [Memory Leak](memory-leak.md)
- [Deployment Failure](deployment-failure.md)

---

*Last Updated: {{date}}*
*Reviewed by: SRE Team*
*Next Review: {{date+30d}}*
```
