# ADR-005: Attachments in private S3-compatible object storage

- **Status:** Accepted (2026-10-29)
- **Context:** Render's service filesystem is ephemeral; attachments must survive deploys.
- **Decision:** Bytes in a private Cloudflare R2 bucket (`document-workspace-attachments`);
  metadata in PostgreSQL. Object keys are `documents/{doc}/attachments/{uuid}` — never derived
  from user input. Downloads stream through the API after authorization with
  `Content-Disposition: attachment` and `nosniff` (no public or pre-signed URLs, no bucket CORS).
  Local/CI use moto (in-memory S3 API); `minio/minio` could not be pulled from Docker Hub.
- **Alternatives:** Render disk (paid, single instance); pre-signed URLs (less control, CORS).
- **Consequences:** Durable storage with credentials to manage; API bandwidth carries downloads
  (fine at 10 MB limit). No virus scanning yet (#29).
- **Revisit when:** large files, high download volume (switch to short-lived signed URLs), or
  malware scanning (#29).
