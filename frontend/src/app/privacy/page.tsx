export default function PrivacyPage() {
  return (
    <div className="min-h-screen bg-[#0A0908] text-[#C4BBB5]">

      {/* Nav */}
      <nav className="border-b border-white/5 px-6 py-4 flex items-center justify-between max-w-4xl mx-auto">
        <a href="/" className="font-display text-[#F5F1ED] text-lg">OneGoal Pro</a>
        <a href="/" className="text-[#5C524A] text-sm hover:text-[#C4BBB5] transition-colors">← Back</a>
      </nav>

      <div className="max-w-3xl mx-auto px-6 py-16 pb-24">

        {/* Header */}
        <div className="mb-12">
          <p className="text-[#F59E0B] text-xs uppercase tracking-widest font-mono mb-4">Legal</p>
          <h1 className="font-display text-4xl text-[#F5F1ED] mb-4">Privacy Policy</h1>
          <p className="text-[#5C524A] text-sm font-mono">Last updated: March 31, 2026</p>
        </div>

        <div className="space-y-10 text-[15px] leading-relaxed">

          <section>
            <p className="text-[#7A6E65]">
              OneGoal Pro is built on the belief that identity change is personal. This policy explains what we collect, why we collect it, and how we protect it. We don't sell your data. We never will.
            </p>
          </section>

          <section>
            <h2 className="text-[#E8E2DC] font-medium text-lg mb-3">1. Who we are</h2>
            <p className="text-[#7A6E65]">
              OneGoal Pro is operated by One Goal Pro Ltd, a company registered in England and Wales (company number 17127527). If you have questions about this policy, contact us at <a href="mailto:hello@onegoalpro.app" className="text-[#F59E0B] hover:underline">hello@onegoalpro.app</a>.
            </p>
          </section>

          <section>
            <h2 className="text-[#E8E2DC] font-medium text-lg mb-3">2. What we collect</h2>
            <div className="space-y-4 text-[#7A6E65]">
              <div className="border-l border-white/10 pl-4">
                <p className="text-[#C4BBB5] font-medium mb-1">Account information</p>
                <p>Your name, email address, and authentication method (email/password or Google). Required to create and maintain your account.</p>
              </div>
              <div className="border-l border-white/10 pl-4">
                <p className="text-[#C4BBB5] font-medium mb-1">Interview and goal data</p>
                <p>Your responses during the Discovery Interview, your synthesised goal, identity traits, and daily tasks. This is the core of the product — it cannot function without it.</p>
              </div>
              <div className="border-l border-white/10 pl-4">
                <p className="text-[#C4BBB5] font-medium mb-1">Coach conversations</p>
                <p>Messages between you and the AI coach are stored to provide session memory and continuity. The coach cannot know your history without this.</p>
              </div>
              <div className="border-l border-white/10 pl-4">
                <p className="text-[#C4BBB5] font-medium mb-1">Reflections and task history</p>
                <p>Your daily task completions, reflection answers, and progress scores. Used to calculate your transformation score and adapt your coaching over time.</p>
              </div>
              <div className="border-l border-white/10 pl-4">
                <p className="text-[#C4BBB5] font-medium mb-1">Usage data</p>
                <p>Session activity, feature usage, and error logs. Used to improve the product. Collected via PostHog (analytics) and Sentry (error tracking).</p>
              </div>
              <div className="border-l border-white/10 pl-4">
                <p className="text-[#C4BBB5] font-medium mb-1">Payment information</p>
                <p>Billing is handled entirely by Stripe. We store your subscription status and plan but never see or store your card details.</p>
              </div>
              <div className="border-l border-white/10 pl-4">
                <p className="text-[#C4BBB5] font-medium mb-1">Push notification tokens</p>
                <p>If you grant permission, we store a device token to send daily task reminders. You can revoke this at any time through your device settings.</p>
              </div>
            </div>
          </section>

          <section>
            <h2 className="text-[#E8E2DC] font-medium text-lg mb-3">3. How we use your data</h2>
            <div className="space-y-2 text-[#7A6E65]">
              <p>— To deliver the product: generate your goal, daily tasks, coaching responses, and progress tracking.</p>
              <p>— To personalise your experience: the AI uses your history to provide contextual, non-generic coaching.</p>
              <p>— To send notifications: daily task reminders and re-engagement emails if you've been inactive.</p>
              <p>— To process payments: managing your subscription via Stripe.</p>
              <p>— To improve the product: understanding where users drop off, what's working, and what isn't.</p>
            </div>
          </section>

          <section>
            <h2 className="text-[#E8E2DC] font-medium text-lg mb-3">4. AI and your data</h2>
            <p className="text-[#7A6E65] mb-3">
              OneGoal Pro uses OpenAI's API to power the Discovery Interview and AI Coach. Your messages are sent to OpenAI for processing. OpenAI does not use API data to train their models by default. You can review OpenAI's data usage policy at <a href="https://openai.com/policies/api-data-usage-policies" className="text-[#F59E0B] hover:underline" target="_blank" rel="noopener noreferrer">openai.com</a>.
            </p>
            <p className="text-[#7A6E65]">
              We do not use your personal data to train any AI model. Your goal, your story, and your conversations are yours.
            </p>
          </section>

          <section>
            <h2 className="text-[#E8E2DC] font-medium text-lg mb-3">5. Who we share data with</h2>
            <div className="space-y-2 text-[#7A6E65]">
              <p>We do not sell your data to anyone.</p>
              <p>We share data only with the services that power the product:</p>
              <div className="mt-3 space-y-2 pl-4 border-l border-white/10">
                <p><span className="text-[#C4BBB5]">Supabase</span> — database and authentication</p>
                <p><span className="text-[#C4BBB5]">OpenAI</span> — AI interview and coaching</p>
                <p><span className="text-[#C4BBB5]">Stripe</span> — payment processing</p>
                <p><span className="text-[#C4BBB5]">Resend</span> — transactional email</p>
                <p><span className="text-[#C4BBB5]">PostHog</span> — product analytics</p>
                <p><span className="text-[#C4BBB5]">Sentry</span> — error monitoring</p>
                <p><span className="text-[#C4BBB5]">Vercel / Railway</span> — hosting infrastructure</p>
              </div>
            </div>
          </section>

          <section>
            <h2 className="text-[#E8E2DC] font-medium text-lg mb-3">6. Data retention</h2>
            <p className="text-[#7A6E65]">
              We keep your data for as long as your account is active. Coach conversation history is retained to maintain coaching continuity — the coach cannot remember you without it. If you delete your account, all personal data is permanently deleted within 30 days.
            </p>
          </section>

          <section>
            <h2 className="text-[#E8E2DC] font-medium text-lg mb-3">7. Your rights</h2>
            <div className="space-y-2 text-[#7A6E65]">
              <p>You have the right to:</p>
              <p>— <span className="text-[#C4BBB5]">Access</span> all data we hold about you (available via Settings → Export data)</p>
              <p>— <span className="text-[#C4BBB5]">Delete</span> your account and all associated data (available via Settings → Delete account)</p>
              <p>— <span className="text-[#C4BBB5]">Correct</span> inaccurate information</p>
              <p>— <span className="text-[#C4BBB5]">Object</span> to processing for marketing purposes</p>
              <p className="mt-3">To exercise any of these rights, email <a href="mailto:hello@onegoalpro.app" className="text-[#F59E0B] hover:underline">hello@onegoalpro.app</a>.</p>
            </div>
          </section>

          <section>
            <h2 className="text-[#E8E2DC] font-medium text-lg mb-3">8. Cookies</h2>
            <p className="text-[#7A6E65]">
              We use only functional cookies required for authentication and session management. We do not use advertising cookies or third-party tracking cookies.
            </p>
          </section>

          <section>
            <h2 className="text-[#E8E2DC] font-medium text-lg mb-3">9. Security</h2>
            <p className="text-[#7A6E65]">
              All data is encrypted in transit (TLS) and at rest. Authentication is handled by Supabase with JWT tokens. We do not store passwords in plain text. We monitor for errors and anomalies via Sentry.
            </p>
          </section>

          <section>
            <h2 className="text-[#E8E2DC] font-medium text-lg mb-3">10. Changes to this policy</h2>
            <p className="text-[#7A6E65]">
              If we make material changes, we'll notify you by email. The latest version is always at onegoalpro.app/privacy.
            </p>
          </section>

          <section className="border-t border-white/5 pt-8">
            <p className="text-[#3D3630] text-sm">
              Questions? Email <a href="mailto:hello@onegoalpro.app" className="text-[#5C524A] hover:text-[#F59E0B] transition-colors">hello@onegoalpro.app</a>
            </p>
          </section>

        </div>
      </div>
    </div>
  )
}