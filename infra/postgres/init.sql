-- Local development databases. The app role used in staging/production is
-- created by infra/postgres/roles.sql (see ADR-0003); locally the owner role is used.
CREATE DATABASE sallimha_e2e OWNER sallimha;
