# Access Control Policy

**Policy Type:** Access Control Policy
**Version:** {{ version | default("1.0") }}
**Last Updated:** {{ date | default("YYYY-MM-DD") }}
**Owner:** {{ owner | default("[Designated Security Lead]") }}

## 1. Purpose

This policy establishes requirements for controlling logical and physical access to organizational information systems, data, and facilities to protect the confidentiality, integrity, and availability of information assets.

**Applicable Controls:** {{ controls.CC6_1 | default("[CC6.1 — not yet assessed]") }}, {{ controls.CC6_2 | default("[CC6.2 — not yet assessed]") }}, {{ controls.CC6_3 | default("[CC6.3 — not yet assessed]") }}, {{ controls.CC6_6 | default("[CC6.6 — not yet assessed]") }}, {{ controls.CC6_7 | default("[CC6.7 — not yet assessed]") }}, {{ controls.CC6_8 | default("[CC6.8 — not yet assessed]") }}

## 2. Scope

This policy applies to all employees, contractors, and third-party users who access organizational information systems, applications, and data. It covers both logical access (system accounts, application access) and physical access (facilities, data centers).

## 3. Account Management

### 3.1 Account Provisioning

- Access is granted based on the principle of least privilege
- All access requests require manager approval before provisioning
- Role-based access control (RBAC) is the primary access model
- Shared or generic accounts are prohibited unless explicitly approved by the CISO

**Controls:** {{ controls.CC6_1 | default("[CC6.1]") }}, {{ controls.CC6_2 | default("[CC6.2]") }}

### 3.2 Account Review

- User access rights are reviewed quarterly by system owners
- Privileged accounts are reviewed monthly
- Dormant accounts (no login > 90 days) are disabled automatically
- Terminated employees have access revoked within 24 hours of separation

### 3.3 Account Deprovisioning

- HR notifies IT of all terminations and role changes within 4 hours
- Access is revoked before the employee's last day (involuntary) or on the last day (voluntary)
- Shared credentials are rotated when any user with knowledge departs

## 4. Authentication Requirements

### 4.1 Password Policy

- Minimum 12 characters with complexity requirements
- Passwords expire every 90 days for privileged accounts
- Password reuse prohibited for the last 12 passwords
- Account lockout after 5 failed attempts within 15 minutes

### 4.2 Multi-Factor Authentication

- MFA is required for all remote access
- MFA is required for all privileged account access
- MFA is required for access to production systems and data
- Approved MFA methods: hardware tokens, authenticator apps, push notifications

**Controls:** {{ controls.CC6_1 | default("[CC6.1]") }}, {{ controls.CC6_6 | default("[CC6.6]") }}

## 5. Authorization and Least Privilege

- Access is granted on a need-to-know, need-to-do basis
- Separation of duties is enforced for critical functions (e.g., code deployment, financial transactions)
- Elevated privileges require separate accounts from standard user accounts
- Just-in-time (JIT) access is preferred for administrative tasks

**Controls:** {{ controls.CC6_3 | default("[CC6.3]") }}

## 6. Remote Access

- VPN or zero-trust network access is required for all remote connections
- Split tunneling is prohibited
- Remote access sessions time out after 30 minutes of inactivity
- Personal devices must meet minimum security standards before access is granted

**Controls:** {{ controls.CC6_7 | default("[CC6.7]") }}

## 7. Third-Party Access

- Third-party access requires a signed agreement and data processing addendum
- Access is limited to the minimum necessary for the contracted service
- Third-party accounts are reviewed quarterly and disabled when no longer needed
- Third-party access is logged and monitored

**Controls:** {{ controls.CC6_8 | default("[CC6.8]") }}

## 8. Monitoring and Logging

- All access events (login, logout, privilege escalation, access denial) are logged
- Logs are retained for a minimum of 12 months
- Anomalous access patterns trigger automated alerts
- Access logs are reviewed as part of quarterly access reviews

## 9. Enforcement

Violations of this policy may result in disciplinary action, including termination of employment or contract. Violations that constitute criminal activity will be reported to law enforcement.

## 10. References

- NIST SP 800-53 Rev 5: AC family (Access Control)
- {{ controls.CC6_1 | default("[CC6.1]") }}: Logical and Physical Access Controls
- {{ controls.CC6_2 | default("[CC6.2]") }}: Prior to Issuing System Credentials
- {{ controls.CC6_3 | default("[CC6.3]") }}: Role-Based Access and Least Privilege
- {{ controls.CC6_6 | default("[CC6.6]") }}: Logical Access Security Measures
- {{ controls.CC6_7 | default("[CC6.7]") }}: Restriction and Management of System Access
- {{ controls.CC6_8 | default("[CC6.8]") }}: Controls to Prevent or Detect Unauthorized Access
