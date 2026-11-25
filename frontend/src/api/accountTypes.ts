// A player's own account (SPEC_V4 §11, §12.4), mirroring backend/app/{legal,account,email}/routes.py.

export type LegalKind = 'terms' | 'privacy'

export interface LegalText {
  kind: LegalKind
  version: string
  markdown: string
}

/** The emails a player can turn off, in two groups. */
export interface EmailPreferences {
  credits_balance: boolean
  credits_added: boolean
}

export type EmailGroup = keyof EmailPreferences

export interface AccountApi {
  /** Public: the terms or privacy text and the current terms version. */
  legal(kind: LegalKind): Promise<LegalText>
  /** Accept the version the page showed (409 if it changed meanwhile). */
  acceptTerms(version: string): Promise<void>
  /** Everything that's the player's, as a zip (429 if asked again too soon). */
  exportData(): Promise<{ filename: string; blob: Blob }>
  /** Delete the account for good; `confirmName` must be the player's name. Signs out. */
  deleteAccount(confirmName: string): Promise<void>
  emailPreferences(): Promise<EmailPreferences>
  updateEmailPreferences(change: Partial<EmailPreferences>): Promise<EmailPreferences>
  /** Public: the one-click link from an email. */
  unsubscribe(token: string): Promise<{ group: EmailGroup }>
}
