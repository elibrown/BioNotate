# MADA Agent Glossary

Terms used by the MADA agent, a service that guides a non-doctor crew member through an on-board medical emergency and returns the matching ISS emergency Protocol.

## People

**Responder**: The crew member using the app during an emergency; not medically trained.
_Avoid_: user, operator, treating member, caregiver

**Patient**: The crew member who is having the emergency; may be the same person as the Responder.
_Avoid_: astronaut (in instructions), victim, subject

**Crew Medical Officer**: The medically trained person who takes over care; summoned to the scene in every emergency. Written in full in anything a Responder reads.
_Avoid_: CMO (in user-facing text), attending medical officer, Flight Surgeon, doctor

## Protocols

**Protocol**: One emergency action checklist from the ISS Medical Checklist, identified by an ID such as `ANAPHYLAXIS`.
_Avoid_: rule, guideline, procedure, treatment plan

**Step**: One numbered instruction within a Protocol, always shown word for word as written in the source.
_Avoid_: action item, instruction (when it means a Protocol line)

**Universal first steps**: The two Steps that open every response: scene safety (including removing whatever triggered the emergency) and calling the Crew Medical Officer.
_Avoid_: preamble, step 0

**Severity**: The fixed urgency of a Protocol, either life-threatening or urgent; a response takes the highest Severity among its Protocols.
_Avoid_: risk level, acuity, priority, triage score

## Assessment

**Assessment**: One emergency conversation, from the Responder's first description until Protocols are given or the agent concludes none match.
_Avoid_: session, case, consultation, chat

**Round**: One exchange within an Assessment in which the agent asks Checks and the Responder answers them.
_Avoid_: turn (a turn is a single message), iteration

**Check**: A simple, real-time observation or measurement a Responder can make without medical training, such as counting a pulse or photographing a rash.
_Avoid_: test, measurement, biomarker, question

**Check catalogue**: The closed list of Checks the agent is allowed to ask for; anything outside it is never requested.
_Avoid_: question bank, symptom list

**Fast path**: Going straight to a life-threatening Protocol on the first message, without asking Checks, because waiting would cost the Patient's life.
_Avoid_: shortcut, emergency mode

**Glasgow Coma Scale (GCS)**: A Check that rates the Patient's eye, verbal and motor responses; reported as its three components, with a total only when every component could be tested.
_Avoid_: coma score, consciousness score

**GCS alert**: A statement that the Patient's GCS has fallen between two readings in the same Assessment by enough to meet an escalation rule.
_Avoid_: deterioration score, GCS warning

**Degraded response**: A response built without the model's judgement, containing the Universal first steps and the Protocols retrieval found most likely.
_Avoid_: fallback, error response
