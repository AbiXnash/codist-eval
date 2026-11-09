# Codist: a private AI code reviewer for Java and Spring Boot teams

## The problem it answers

In a typical Java microservices team, a developer pushes a change that touches several files across services. The
reviewer is busy and skims it between meetings; a missing null check or a wrong calculation slips through. The bug
reaches customers, an alert fires at night, and the on-call engineer spends hours in logs to find which line and
which change broke it. AI review tools could help, but most send the source code to outside servers, which many
companies, banks and public bodies do not allow, so these teams go without.

## What Codist is

An open-source program a developer runs on their own laptop next to the repository. It watches the repository and
shows its findings in the browser. Nothing leaves the machine: the AI model runs locally through Ollama.

- **Review**: every commit gets 15 exact code checks within seconds, then a local AI model (qwen2.5-coder 7B or 14B)
  reads recent commits in the background. Each AI claim must quote the code it is about; claims the code does not
  back are shown as notes, not facts. Issues are followed until a later commit fixes them.
- **Behaviour** (optional): Codist builds the code before and after a commit, calls the changed methods with the
  same inputs, and shows "this returned 1200 and now returns 1201: was that meant?".
- **Graph**: services, classes and methods, with Feign calls between services and what each commit can affect.
- **Incidents**: paste production logs; Codist finds each Java error, the line of code, the commit that last changed
  it, and suggests a cause.
- **Feedback**: developers mark findings useful or wrong; wrong ones are not reported again, and the AI is shown
  the team's judgements as examples so it learns what this team considers a real problem.
- **Risk ranking**: a small machine-learning model, trained on the repository's own history in seconds, learns which
  kinds of commits needed fixes later and makes the AI read the riskiest commits first. It tests itself and is only
  used when it ranks clearly better than chance (on the jsoup project it ranked a bug-bringing commit above a safe
  one 82% of the time).

## How it is delivered

One file to install (macOS, Linux, Windows) with a one-line installer; needs git, and optionally Java 21, Maven and a
local model server. Source available on GitHub (abxengg/codist), free for noncommercial use, first release v0.1.0 in November 2026. No account, no
cloud, no subscription.

## What has been measured (honestly)

- On 118 real bugs from open-source Java projects, the 14B local model put a finding within 3 lines of 95 bugs, and clearly named 51 of them.
- Running changed code before and after found the real difference in 5 of 10 sample bugs, with no false alarm on 22
  refactoring commits that should not change behaviour.
- Speed: code checks take milliseconds per commit; the 14B model takes about 6 minutes per commit on a 16 GB laptop,
  so it reads only the newest 50 commits by default.

## Known weaknesses

- Only Java (Spring Boot), and Maven for the behaviour feature; Gradle not yet.
- A laptop model is slow and finds fewer bugs than large cloud models.
- Spring services that use databases or other services cannot yet be run by the behaviour feature.
- Built by a very small team; Windows support is untested.

## Alternatives people compare it with

Cloud AI reviewers (CodeRabbit, Qodo, GitHub Copilot code review), static analysers (SonarQube, Semgrep, SpotBugs,
Error Prone), and plain human review.
