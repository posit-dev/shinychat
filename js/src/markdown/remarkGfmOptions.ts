/**
 * Shared options for remark-gfm.
 *
 * `singleTilde: false` requires double tildes (`~~text~~`) for strikethrough,
 * so single tildes used for approximation (`~$1.50`), Unix paths (`~/Documents`),
 * etc. render as literal text instead of triggering strikethrough.
 *
 * See: https://github.com/posit-dev/shinychat/issues/349
 */
export const remarkGfmOptions = { singleTilde: false } as const
