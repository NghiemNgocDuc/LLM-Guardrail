import AppIcon from "./AppIcon";
import RequestJourney from "./RequestJourney";

export default function AuthWelcome() {
  return (
    <section className="gr-auth-story" aria-labelledby="gr-auth-hero-title">
      <p className="gr-auth-eyebrow"><AppIcon name="sparkles" size={15} /> GOOD IDEAS. CLEAR BOUNDARIES.</p>
      <h2 id="gr-auth-hero-title" className="gr-auth-story-title"><span className="gr-auth-title-lead">Helpful AI.</span><span className="gr-auth-title-accent">A little peace of mind.<svg viewBox="0 0 560 24" preserveAspectRatio="none" aria-hidden="true"><path d="M4 18C135 4 335 3 554 13" /></svg></span></h2>
      <p className="gr-auth-story-description">A guardrail is a thoughtful check between you and AI. Catch private details and risky instructions, with clear reasons when something needs attention.</p>
      <RequestJourney />
      <p className="gr-auth-story-note"><AppIcon name="help" size={16} /><span>A little curiosity goes a long way. Try an example above.</span></p>
    </section>
  );
}
