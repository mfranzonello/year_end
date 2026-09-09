-- No user accounts, preapprovals, or roles assigned to real identities.
INSERT INTO users.roles (role_name) VALUES ('demo'), ('viewer'), ('member'), ('admin');
INSERT INTO users.issuers (issuer_name) VALUES ('Google');
