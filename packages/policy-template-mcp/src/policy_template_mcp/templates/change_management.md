# Change Management Policy

**Policy Type:** Change Management Policy
**Version:** {{ version | default("1.0") }}
**Last Updated:** {{ date | default("YYYY-MM-DD") }}
**Owner:** {{ owner | default("[Designated Security Lead]") }}

## 1. Purpose

This policy establishes requirements for managing changes to information systems, infrastructure, and applications to minimize disruption, ensure integrity, and maintain security controls throughout the change lifecycle.

**Applicable Controls:** {{ controls.CC8_1 | default("[CC8.1 — not yet assessed]") }}

## 2. Scope

This policy applies to all changes to production information systems, including application code, infrastructure configuration, database schemas, network configurations, and security controls. Emergency changes and standard pre-approved changes follow modified procedures defined in this document.

## 3. Change Classification

| Type | Description | Approval | Lead Time |
|------|-------------|----------|-----------|
| Standard | Pre-approved, low-risk, repeatable (e.g., certificate rotation) | Pre-approved catalog | None |
| Normal | Planned change with known risk profile | Change Advisory Board (CAB) | 5 business days |
| Emergency | Unplanned change to restore service or patch critical vulnerability | Emergency CAB (2 approvers) | Immediate |

## 4. Change Request Process

### 4.1 Submission

- All changes are submitted through the change management system
- Each request includes: description, business justification, risk assessment, rollback plan, and testing evidence
- The requestor must not be the sole approver (separation of duties)

### 4.2 Risk Assessment

- Impact analysis covering affected systems, users, and integrations
- Security impact assessment for changes affecting authentication, authorization, or data handling
- Availability impact assessment including maintenance window requirements

### 4.3 Approval

- Standard changes: auto-approved against the pre-approved catalog
- Normal changes: CAB review with documented approval
- Emergency changes: two authorized approvers from the emergency CAB roster

**Controls:** {{ controls.CC8_1 | default("[CC8.1]") }}

## 5. Development and Testing

### 5.1 Development Standards

- All code changes require peer review (pull request with at least one approval)
- Branch protection rules enforce review requirements
- Static analysis and linting run automatically on every commit
- No direct commits to production branches

### 5.2 Testing Requirements

- Unit tests cover new and modified functionality
- Integration tests validate cross-system interactions
- Security testing for changes affecting authentication, authorization, or data handling
- Performance testing for changes affecting high-traffic paths

### 5.3 Environment Promotion

- Changes progress through: development, staging, production
- Each environment has parity with production configuration
- Staging deployment must succeed before production deployment is approved

## 6. Deployment

### 6.1 Deployment Procedures

- Deployments follow documented runbooks
- Deployments occur within approved maintenance windows (normal changes)
- Deployment verification includes health checks and smoke tests
- Deployment logs are retained for a minimum of 12 months

### 6.2 Rollback

- Every change must have a documented rollback plan
- Rollback procedures are tested before production deployment
- Rollback decision authority rests with the on-call engineer and change owner
- Rollback must be executable within 15 minutes

## 7. Emergency Changes

- Emergency changes bypass the standard CAB process but require two authorized approvers
- Emergency changes are documented retroactively within 2 business days
- Root cause analysis is completed within 5 business days
- Emergency change patterns are reviewed monthly for catalog additions

## 8. Monitoring and Review

- All changes are tracked in the change management system
- Failed changes are reviewed in the next CAB meeting
- Change success rate is reported monthly
- This policy is reviewed and updated annually

## 9. References

- NIST SP 800-53 Rev 5: CM family (Configuration Management), SA family (System and Services Acquisition)
- {{ controls.CC8_1 | default("[CC8.1]") }}: Changes to Infrastructure, Data, Software, and Procedures
