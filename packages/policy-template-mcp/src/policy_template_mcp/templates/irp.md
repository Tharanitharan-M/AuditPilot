# Incident Response Plan

**Policy Type:** Incident Response Plan (IRP)
**Version:** {{ version | default("1.0") }}
**Last Updated:** {{ date | default("YYYY-MM-DD") }}
**Owner:** {{ owner | default("[Designated Security Lead]") }}

## 1. Purpose

This Incident Response Plan establishes procedures for identifying, containing, eradicating, and recovering from security incidents that may affect the confidentiality, integrity, or availability of organizational information systems and data.

**Applicable Controls:** {{ controls.CC7_1 | default("[CC7.1 — not yet assessed]") }}, {{ controls.CC7_2 | default("[CC7.2 — not yet assessed]") }}, {{ controls.CC7_3 | default("[CC7.3 — not yet assessed]") }}, {{ controls.CC7_4 | default("[CC7.4 — not yet assessed]") }}

## 2. Scope

This plan applies to all information systems, networks, and data under organizational control. All employees, contractors, and third-party service providers with access to organizational systems are subject to this plan.

## 3. Incident Classification

| Severity | Description | Response Time | Escalation |
|----------|-------------|---------------|------------|
| Critical | Active data breach, ransomware, complete system compromise | Immediate (< 15 min) | CISO + Legal + Executive |
| High | Confirmed unauthorized access, malware outbreak | < 1 hour | Security Lead + CISO |
| Medium | Suspicious activity, policy violation, failed intrusion attempt | < 4 hours | Security Lead |
| Low | Informational alert, minor policy deviation | < 24 hours | Security Analyst |

## 4. Incident Response Phases

### 4.1 Preparation

- Maintain an up-to-date incident response team roster with contact information
- Conduct tabletop exercises quarterly
- Ensure logging and monitoring systems are operational ({{ controls.CC7_1 | default("[CC7.1]") }})
- Maintain forensic tools and evidence collection procedures

### 4.2 Detection and Analysis

- Monitor security alerts from SIEM, IDS/IPS, and endpoint detection systems
- Correlate alerts with threat intelligence feeds
- Document initial findings in the incident tracking system
- Assign severity classification per Section 3

**Detection Controls:** {{ controls.CC7_2 | default("[CC7.2 — not yet assessed]") }}

### 4.3 Containment

- **Short-term containment:** Isolate affected systems to prevent lateral movement
- **Long-term containment:** Apply temporary fixes while preparing for eradication
- Preserve forensic evidence before any remediation
- Notify affected parties per legal and regulatory requirements

### 4.4 Eradication

- Remove root cause (malware, unauthorized accounts, vulnerabilities)
- Apply patches and configuration changes
- Verify removal through scanning and monitoring

### 4.5 Recovery

- Restore systems from verified clean backups
- Monitor recovered systems for signs of re-infection
- Validate system integrity before returning to production
- Update monitoring rules based on incident indicators

**Recovery Controls:** {{ controls.CC7_4 | default("[CC7.4 — not yet assessed]") }}

### 4.6 Post-Incident Review

- Conduct a post-incident review within 5 business days of resolution
- Document lessons learned and update this plan accordingly
- Update detection rules and monitoring thresholds
- Provide findings to management for risk assessment updates

**Review Controls:** {{ controls.CC7_3 | default("[CC7.3 — not yet assessed]") }}

## 5. Communication Plan

- Internal notifications follow the escalation matrix in Section 3
- External notifications (customers, regulators, law enforcement) require CISO and Legal approval
- All communications are documented in the incident tracking system
- No public disclosure without executive and legal approval

## 6. Roles and Responsibilities

| Role | Responsibility |
|------|---------------|
| Incident Commander | Overall incident coordination and decision-making |
| Security Analyst | Detection, analysis, and technical response |
| Communications Lead | Internal and external communication |
| Legal Counsel | Regulatory compliance and notification requirements |
| System Administrator | System isolation, recovery, and restoration |

## 7. Testing and Maintenance

- This plan is reviewed and updated at least annually
- Tabletop exercises are conducted quarterly
- Full simulation exercises are conducted annually
- All updates are version-controlled and communicated to the incident response team

## 8. References

- NIST SP 800-61 Rev 2: Computer Security Incident Handling Guide
- NIST SP 800-53 Rev 5: Security and Privacy Controls
- {{ controls.CC7_1 | default("[CC7.1]") }}: Security Operations Monitoring
- {{ controls.CC7_2 | default("[CC7.2]") }}: Detection of Unauthorized or Anomalous Activity
- {{ controls.CC7_3 | default("[CC7.3]") }}: Evaluation of Security Events
- {{ controls.CC7_4 | default("[CC7.4]") }}: Response to Security Incidents
