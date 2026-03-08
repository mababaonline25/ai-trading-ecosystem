### **18.3 sre/error-budgets/policy.md** - এরর বাজেট পলিসি
```markdown
# 🎯 Error Budget Policy

## 📋 Overview

Error budgets are a fundamental concept in Site Reliability Engineering (SRE) that balance service reliability with feature velocity. This document defines our error budget policy for all services in the AI Trading Ecosystem.

## 🎯 Error Budget Definition

**Error Budget = 100% - Service Level Objective (SLO)**

For example:
- If SLO = 99.9%, Error Budget = 0.1% (≈ 43.2 minutes/month)
- If SLO = 99.99%, Error Budget = 0.01% (≈ 4.32 minutes/month)

## 📊 Service Error Budgets

| Service | SLO | Error Budget (monthly) | Measurement Period |
|---------|-----|------------------------|-------------------|
| API Gateway | 99.99% | 4.32 minutes | Rolling 30 days |
| Trading Engine | 99.95% | 21.6 minutes | Rolling 30 days |
| Market Data | 99.9% | 43.2 minutes | Rolling 30 days |
| Database | 99.99% | 4.32 minutes | Rolling 30 days |
| AI Engine | 99.5% | 3.6 hours | Rolling 30 days |

## 🚦 Error Budget States

### 🟢 **Green ( > 80% remaining)**
- Normal operations
- All deployments allowed
- Feature releases permitted
- No restrictions

### 🟡 **Yellow ( 50-80% remaining)**
- Caution mode
- Critical deployments only
- Feature flags required for releases
- Increased monitoring

### 🟠 **Orange ( 20-50% remaining)**
- Warning mode
- Emergency fixes only
- Mandatory code freeze for non-critical
- Daily review meetings

### 🔴 **Red ( < 20% remaining)**
- Critical mode
- No deployments allowed
- Immediate incident response
- Escalate to management

## 🔄 Error Budget Consumption

### What Consumes Error Budget
- Service outages
- High latency incidents
- Failed requests (5xx errors)
- Data corruption
- Security breaches

### What Does NOT Consume Error Budget
- Planned maintenance
- Client-side errors (4xx)
- Rate limiting (429)
- Scheduled downtime

## 📈 Error Budget Tracking

### Prometheus Query
```promql
# Error budget remaining
(1 - (sum(rate(http_requests_total{status=~"5.."}[30d])) / sum(rate(http_requests_total[30d])))) * 100

# Error budget consumption
(sum(rate(http_requests_total{status=~"5.."}[30d])) / sum(rate(http_requests_total[30d]))) * 100

# Time until budget exhaustion
(error_budget_remaining * 30 * 24 * 60) / error_rate_per_minute
```

### Grafana Dashboard
- Real-time error budget visualization
- Historical trends
- Burn rate alerts
- Forecast exhaustion

## 🚨 Error Budget Alerts

### Burn Rate Alerts
```yaml
# Fast burn (10x for 1 hour)
- alert: ErrorBudgetBurnFast
  expr: |
    (
      sum(rate(http_requests_total{status=~"5.."}[1h]))
      /
      sum(rate(http_requests_total[1h]))
    ) > 0.01 * (100 - 99.99) / 100
  for: 1h
  labels:
    severity: critical

# Slow burn (2x for 6 hours)
- alert: ErrorBudgetBurnSlow
  expr: |
    (
      sum(rate(http_requests_total{status=~"5.."}[6h]))
      /
      sum(rate(http_requests_total[6h]))
    ) > 0.02 * (100 - 99.99) / 100
  for: 6h
  labels:
    severity: warning
```

## 🛑 Deployment Policies

### Based on Error Budget Status

| Status | Deployments | Rollback Time | Approval |
|--------|------------|---------------|----------|
| 🟢 Green | All allowed | 30 minutes | Team Lead |
| 🟡 Yellow | Critical only | 15 minutes | Engineering Manager |
| 🟠 Orange | Emergency only | 5 minutes | VP Engineering |
| 🔴 Red | None | N/A | CEO/CTO |

## 📊 Reporting

### Weekly Error Budget Report
- Current status for each service
- Trends over last 30 days
- Major incidents and impact
- Forecast and recommendations

### Monthly Business Review
- Error budget performance
- Reliability investments
- Trade-off decisions
- SLO adjustments

## 🔄 SLO Adjustments

### When to Adjust SLOs
- Sustained error budget pressure
- Business requirement changes
- Infrastructure improvements
- Quarterly review

### Adjustment Process
1. Collect 90 days of data
2. Analyze error patterns
3. Propose new SLO
4. Stakeholder review
5. Implement and monitor

## 📝 Incident Response Based on Error Budget

### Low Error Budget (<20%)
- Immediate incident response
- Full team mobilization
- Hourly status updates
- Executive involvement

### Medium Error Budget (20-50%)
- Prioritized incident response
- Team on-call rotation
- Daily status updates
- Management notified

### High Error Budget (>50%)
- Normal incident response
- Standard procedures
- Regular updates
- Team level

## 🎯 Best Practices

1. **Monitor burn rate**, not just budget
2. **Alert on rate of consumption**
3. **Use multiple windows** (1h, 6h, 3d)
4. **Automate responses** where possible
5. **Document all exceptions**
6. **Review quarterly**
7. **Balance reliability with velocity**

## 📚 References
- [Google SRE Book - Error Budgets](https://sre.google/sre-book/part3-practices/)
- [Prometheus Alerting Rules](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/)
- [Our SLO Definitions](slo/service-level-objectives.yaml)

---

*Last Updated: {{date}}*
*Owner: SRE Team*
*Next Review: {{date+90d}}*
