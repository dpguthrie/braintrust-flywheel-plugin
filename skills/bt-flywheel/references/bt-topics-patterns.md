# bt topics Patterns

Topics automation automatically classifies production traces into topic clusters (e.g., intent, sentiment, task type).
Use it during the Discover phase to understand the distribution of inputs hitting your agent without writing SQL.

---

## Check Topics Status

```bash
# Summary status for the active project
bt topics status -p <project-name>

# Full status with topic-by-topic breakdown
bt topics status -p <project-name> --full

# Watch live for topic updates
bt topics status -p <project-name> --watch
```

---

## View / Edit Topics Config

```bash
# View current config
bt topics config -p <project-name>

# Enable Topics automation
bt topics config enable -p <project-name>

# Tune window and generation cadence
bt topics config set --topic-window 1h --generation-cadence 1d -p <project-name>

# Set embedding model for a specific topic
bt topics config topic-map set <TopicName> --embedding-model brain-embedding-1 -p <project-name>
```

---

## Trigger Reprocessing

```bash
# Queue Topics to run on the next executor pass
bt topics poke -p <project-name>

# Rewind recent history and reprocess (e.g., reprocess last 7 days)
bt topics rewind 7d -p <project-name>
```

---

## Open in Browser

```bash
bt topics open -p <project-name>
```

---

## When to Use During the Flywheel

- **Discover phase**: run `bt topics status --full` to see how production inputs cluster. Use this alongside SQL facet queries to identify underrepresented categories.
- **After agent changes**: run `bt topics poke` to force re-classification if the topic taxonomy has drifted.
- **After structural agent change**: `bt topics rewind 7d` to reprocess recent traces with updated topic definitions.
