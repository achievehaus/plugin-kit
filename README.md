# The Achievehaus plugin kit

`achievehaus-plugin` scaffolds, builds, checks, runs and packs an Achievehaus
plugin in Rust, TypeScript, JavaScript, C# or C. Download it for your OS from
[the releases](https://github.com/achievehaus/plugin-kit/releases), then:

    achievehaus-plugin new my-plugin
    cd my-plugin
    achievehaus-plugin doctor
    achievehaus-plugin run

The project it writes depends on the published SDKs (`achievehaus-sdk`,
`@achievehaus/plugin`, `Achievehaus.Plugin`, or the C SDK from a release
here), and its workflow uses the two actions in this repository: `achievehaus/plugin-kit@v<version>`
installs the kit, `achievehaus/plugin-kit/workshop@v<version>` uploads a release to
the Steam Workshop. Its README says the rest.

Released from the Achievehaus repository; changes made here are overwritten.
