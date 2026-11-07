# Questions to ask MiroFish about Codist

Paste one as the prediction requirement, with `seed/codist-brief.md` as the seed material. Start with fewer than 40
rounds and a small number of agents; each round is many model calls.

## 1. Launch reaction (the main test)

Simulate how Java and Spring Boot developers, tech leads, engineering managers and security or compliance officers
at banks, insurers, government agencies and mid-size software companies react over four weeks after Codist is
announced on Hacker News, Reddit r/java and LinkedIn. Predict: who tries it and why, the three strongest objections,
which feature people value most (review, behaviour, graph, incidents, privacy), what would make a team adopt it for
real, and what would make them drop it after a week.

## 2. A company pilot

A 40-developer company with strict rules against sending code to cloud services runs a two-week pilot of Codist on
four Spring Boot microservices, on 16 GB laptops. Simulate the developers, the two reviewers, the on-call engineer,
the security officer and the engineering manager. Predict: day-to-day friction, how they react to a 6-minute AI
review per commit, how many findings they mark wrong, whether the behaviour feature changes how they review, and
whether the manager recommends rolling it out.

## 3. What to build next

Codist's team can build only one of these next: learning from findings marked useful or wrong; a small model that
ranks which commits are riskiest; Gradle support; running Spring services with faked databases and other services;
tested Windows support; a faster model setup for Apple silicon. Simulate the views of developers, tech leads and
managers at companies like those in question 1. Predict which one most increases adoption and which matters least.

## 4. Against the alternatives

Simulate a team choosing between Codist, a cloud AI reviewer (CodeRabbit or GitHub Copilot review), SonarQube, and
doing nothing. Predict which they choose, the deciding reasons, and under what conditions Codist wins.
