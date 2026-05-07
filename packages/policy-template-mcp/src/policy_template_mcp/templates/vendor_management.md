# Vendor Management Policy

**Policy Type:** Vendor Management Policy
**Version:** {{ version | default("1.0") }}
**Last Updated:** {{ date | default("YYYY-MM-DD") }}
**Owner:** {{ owner | default("[Designated Security Lead]") }}

## 1. Purpose

This policy establishes requirements for evaluating, onboarding, monitoring, and offboarding third-party vendors and service providers to ensure they meet organizational security, privacy, and compliance requirements.

**Applicable Controls:** {{ controls.CC9_1 | default("[CC9.1 — not yet assessed]") }}, {{ controls.CC9_2 | default("[CC9.2 — not yet assessed]") }}

## 2. Scope

This policy applies to all third-party vendors, service providers, and business partners that access, process, store, or transmit organizational data or connect to organizational systems. This includes SaaS providers, infrastructure providers, managed service providers, and professional service firms.

## 3. Vendor Classification

| Tier | Criteria | Review Frequency | Assessment Depth |
|------|----------|-----------------|-----------------|
| Critical | Processes sensitive data, critical to operations, single point of failure | Quarterly | Full security assessment |
| High | Accesses production systems or PII, significant business impact | Semi-annually | Security questionnaire + evidence review |
| Medium | Limited data access, moderate business impact | Annually | Security questionnaire |
| Low | No data access, minimal business impact | Biannually | Self-declaration |

## 4. Vendor Evaluation and Onboarding

### 4.1 Due Diligence

- Security questionnaire (SIG-Lite or equivalent) completed by vendor
- Review of vendor's draft readiness posture (SOC 2 Type II, ISO 27001, or equivalent)
- Review of vendor's data handling practices and privacy policies
- Financial stability assessment for Critical and High tier vendors

### 4.2 Risk Assessment

- Data classification of information shared with the vendor
- Assessment of vendor's access requirements (network, system, data)
- Evaluation of vendor's incident response capabilities
- Assessment of regulatory implications (data residency, cross-border transfer)

### 4.3 Contractual Requirements

- Data processing agreement (DPA) or equivalent
- Right to assess and review security controls
- Incident notification requirements (within 24 hours of discovery)
- Data return and destruction obligations upon termination
- Insurance requirements proportional to risk tier

**Controls:** {{ controls.CC9_1 | default("[CC9.1]") }}

## 5. Ongoing Monitoring

### 5.1 Performance Monitoring

- Service level agreements (SLAs) tracked and reported quarterly
- Availability and uptime metrics reviewed monthly for Critical tier vendors
- Issue and incident tracking with vendor responsibility documented

### 5.2 Security Monitoring

- Vendor security posture reviewed per tier schedule (Section 3)
- Significant changes to vendor's security posture trigger re-assessment
- Vendor breach notifications tracked and escalated per Section 7
- Subprocessor changes reviewed and approved before implementation

### 5.3 Compliance Monitoring

- Annual review of vendor certifications and compliance reports
- Regulatory changes that affect vendor requirements tracked and communicated
- Vendor compliance with contractual obligations verified during reviews

**Controls:** {{ controls.CC9_2 | default("[CC9.2]") }}

## 6. Vendor Access Management

- Vendor access follows the principle of least privilege
- Vendor accounts use MFA and are separate from employee accounts
- Vendor access is time-limited and reviewed quarterly
- Vendor access is revoked immediately upon contract termination or significant security event

## 7. Incident Management

- Vendors must notify the organization within 24 hours of a confirmed security incident
- Vendor incidents affecting organizational data are managed under the Incident Response Plan
- Post-incident review includes vendor's root cause analysis and remediation plan
- Repeated incidents may trigger contract review or termination

## 8. Vendor Offboarding

- All organizational data returned or destroyed with certified confirmation
- All vendor access credentials revoked
- Network and system access removed
- Final security review completed
- Offboarding documented in the vendor management system

## 9. Governance

- Vendor inventory maintained and updated quarterly
- Vendor risk register reviewed by the security team quarterly
- This policy is reviewed and updated annually
- Exceptions require CISO approval and are documented with compensating controls

## 10. References

- NIST SP 800-53 Rev 5: SA family (System and Services Acquisition), SR family (Supply Chain Risk Management)
- {{ controls.CC9_1 | default("[CC9.1]") }}: Risk Mitigation Activities for Vendor Management
- {{ controls.CC9_2 | default("[CC9.2]") }}: Vendor and Business Partner Risk Assessment
