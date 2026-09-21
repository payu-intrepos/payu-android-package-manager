# payu-android-maven

Public Maven host for PayU Android SDKs. No GitHub token is required to download.

```text
https://payu-intrepos.github.io/payu-android-maven/
```

```kotlin
repositories {
    google()
    mavenCentral()
    maven { url = uri("https://payu-intrepos.github.io/payu-android-maven/") }
}

dependencies {
    implementation("in.payu:payu-checkout-pro:3.3.15")
}
```

This repository is public-read. Writes and releases are PayU members only (GitLab CI + protected `main`). Do not use GitHub Packages.
