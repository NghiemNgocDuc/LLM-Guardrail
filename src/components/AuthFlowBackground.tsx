export default function AuthFlowBackground() {
  return <div className="gr-auth-background" aria-hidden="true">
    <div className="gr-auth-paper-texture" />
    <svg className="gr-auth-background-orbits" viewBox="0 0 1100 1300" fill="none" preserveAspectRatio="xMidYMin slice">
      <ellipse cx="265" cy="530" rx="435" ry="460" transform="rotate(-22 265 530)" />
      <ellipse cx="265" cy="530" rx="493" ry="522" transform="rotate(-22 265 530)" />
      <ellipse cx="265" cy="530" rx="553" ry="585" transform="rotate(-22 265 530)" />
      <path className="gr-auth-background-branch" d="M42 1040c94-149 218-203 359-203M141 938c-61-11-78-41-83-77 43 4 74 30 83 77ZM203 890c-20-50-7-85 20-113 23 34 20 73-20 113ZM283 855c5-54 32-80 69-93 6 41-17 75-69 93Z" />
      <circle cx="672" cy="232" r="6" className="gr-auth-background-node" />
      <circle cx="684" cy="871" r="4" className="gr-auth-background-node" />
      <path d="M744 157v22m-11-11h22M124 1191v16m-8-8h16" />
    </svg>
    <div className="gr-auth-background-wash" />
  </div>;
}
