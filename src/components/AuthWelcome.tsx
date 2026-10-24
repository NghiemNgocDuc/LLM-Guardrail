import AppIcon from "./AppIcon";
import RequestJourney from "./RequestJourney";

export default function AuthWelcome() {
  return (
    <section className="gr-auth-story" aria-labelledby="gr-auth-hero-title">
      <p className="gr-auth-eyebrow"><AppIcon name="sparkles" size={16} /> A LITTLE CLARITY. A LOT OF POSSIBILITY.</p>
      <h2 id="gr-auth-hero-title" className="gr-auth-story-title">Helpful AI.<br /><span>A little peace of mind.</span></h2>
      <p className="gr-auth-story-description">A guardrail is a quick check between you and AI. Catch private details and risky instructions, and see why a message was allowed or stopped.</p>
      <RequestJourney />
      <p className="gr-auth-story-note"><AppIcon name="help" size={16} /> Curious? Try an example. No account needed.</p>
    </section>
  );
}
