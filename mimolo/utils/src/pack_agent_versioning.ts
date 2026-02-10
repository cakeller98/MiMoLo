import semver from "semver";

export type ReleaseType = "major" | "minor" | "patch";
export type PrereleaseType = "alpha" | "beta" | "rc";

export function bumpVersion(
  current: string,
  release?: ReleaseType,
  prerelease?: PrereleaseType,
): string {
  if (release && prerelease) {
    const preKey =
      release === "major" ? "premajor" : release === "minor" ? "preminor" : "prepatch";
    return semver.inc(current, preKey, prerelease) ?? current;
  }
  if (release) {
    return semver.inc(current, release) ?? current;
  }
  if (prerelease) {
    return semver.inc(current, "prerelease", prerelease) ?? current;
  }
  return current;
}
