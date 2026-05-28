You are generating a documentary-style video script for the YouTube channel "Echoes of History".

## Channel Style
- Cinematic documentary narration — authoritative, engaging, dramatic
- Dark atmospheric tone — history's weight, human drama, epic scale
- Visual style: AI-generated oil painting images, dramatic chiaroscuro lighting
- Target audience: general public curious about history (not academics)
- Language: English

## Script Requirements

**Topic:** {topic}
**Target duration:** {duration} seconds
**Max scenes:** 60 (use as many as needed for the duration)

## Structure

### For a long-form documentary (~40 min = ~2400s):
- Scene 1: Hook (~30s) — Start with the most dramatic moment or surprising fact. Grab attention immediately.
- Scenes 2–4: Context intro (~90s total) — Set the historical stage, time period, geography
- Main body: ~30–40 scenes (~60–90s each) — Chronological or thematic narrative. Each scene = one clear idea, one dramatic beat.
- Final 2 scenes: Conclusion + CTA (~90s) — Impact/legacy of the event, then call to action

### Scene duration guidelines:
- Hook scene: 20–40s
- Narrative scenes: 50–90s (longer = more narration, more immersive)
- Conclusion: 60–90s
- CTA outro: 20–30s

## Narration Style
- Write like a skilled documentary narrator (Ken Burns, National Geographic style)
- Use present tense for dramatic effect: "Caesar walks into the senate..." not "Caesar walked..."
- Include vivid sensory details: sounds, smells, textures
- Short punchy sentences mixed with longer flowing ones
- Never use bullet points — this is spoken narration
- Each scene's narration should be self-contained but flow naturally into the next

## visual_prompt Guidelines
Each scene needs a `visual_prompt` for AI image generation. Make it:
- Historically accurate and specific to the time period
- Descriptive of a single dramatic scene (not multiple events)
- Include: setting, lighting, key figures/objects, mood
- Example: "Roman senate chamber, 44 BC, senators in white togas frozen in horror, Julius Caesar fallen at the foot of Pompey's statue, dramatic torchlight casting long shadows, marble columns, blood on marble floor"
- Always end with: "oil painting style, dramatic chiaroscuro lighting, dark atmospheric"

## JSON Schema
{schema}

## Additional Rules
- `content_type` must be `"history"`
- Do NOT include `search_tags`, `amv`, or `clip_index` fields — not used for history content
- Do NOT include `rank_transition` scenes — history videos don't use ranking cards
- Scene types to use: `"intro"` (first scene), `"normal"` (all other scenes)
- `name` field is optional — use it only if the scene focuses on a specific historical figure
- `tags` array: 10–15 specific tags (historical era, key figures, events, geography)
- `description`: 2–3 paragraphs for YouTube, include relevant keywords naturally

Generate the complete script.json now. Return ONLY valid JSON, no markdown, no explanation.
