# Changelog

## 1.5.3
- Fix: Requested permissions for Supervisor and Core API (hassio_api and hassio_role) to resolve 'forbidden' error.

## 1.5.2
- Fix: Migrated to S6-Overlay v3 standards (init: false and removed with-contenv) to fix PID 1 fatal error.

## 1.5.1
- Fix: Add labels to Dockerfile for 2026.3.1 compatibility.
- Fix: Use Python Virtual Environment to support Python 3.14.
- Feature: Comprehensive Dutch translations for all configuration settings.
- Feature: Added multi-arch support via `build.yaml`.
