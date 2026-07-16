# writing

The editorial pipeline, generalized from the maintainer's blog system (KICKSTART.md §5.4): ideas → drafts → published, with series and research notes feeding the flow. The source vault's rule is kept: editorial work lives here, the website itself is a software project — link the two, never mix them.

| `type` | `status` | Extra fields | Template |
|---|---|---|---|
| `blog-idea` | `idea` | `topic` | Blog Idea |
| `blog-draft` | `draft` | `topic`, `series`, `slug` | Blog Draft |
| `blog-published` | `published` | `published_url` + draft fields | Published Post |
| `blog-series` | `active` | — | Series Note |
| `blog-research` | `active` | `topic` | Blog Research Note |

`Blog-Pipeline.base` renders Ideas / Drafting / Published / By-Series, tag-driven. Seeded: `00 Dashboard.md`, `Editorial-Calendar.md`, `Content-Backlog.md`. Variables: `root` (default `Writing/Blog`).

Agent layer: `blog-editor` with the `editorial-pipeline` skill. It captures ideas, keeps status metadata and backlog wikilinks truthful, reads publishing rhythm and target dates only from `Editorial-Calendar.md`, and proposes Ideas/Drafts/Published promotions for confirmation before any file move.
