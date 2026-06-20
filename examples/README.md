# Examples

Sample conversations for trying Continuator without your own files.

```bash
continuator continue examples/neck.txt
continuator explain examples/gitissue.txt
```

| File | Size | Notes |
|------|------|-------|
| `neck.txt` | Short | Posture/neck hump tutoring — good first run |
| `gitissue.txt` | Medium | GitHub issue thread |
| `jquery.txt` | Medium | jQuery learning session |

All samples are synthetic or public-style discussions with no personal identifiers.

For a wiring test without downloading the LoRA adapter:

```bash
MEMORY_EXTRACTOR_BACKEND=mock continuator continue examples/neck.txt --quiet
```
