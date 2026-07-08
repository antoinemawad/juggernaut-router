import argparse


def validate_image_ref(image: str) -> list[str]:
    errors = []
    if not image or image in {"juggernaut-router:local", "your-image:latest"}:
        errors.append("image must be a public registry reference, not a local placeholder")
    if "/" not in image.split(":")[0]:
        errors.append("image should include a public registry namespace, for example docker.io/user/name:tag")
    if ":" not in image.rsplit("/", 1)[-1]:
        errors.append("image should include an explicit tag")
    return errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Print final Track 1 image build/push verification commands.")
    parser.add_argument("image", help="Public image reference, for example docker.io/user/juggernaut-router:act2")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    errors = validate_image_ref(args.image)
    if errors:
        for error in errors:
            print("ERROR:", error)
        return 1

    print("# Final linux/amd64 build and push")
    print(f"docker buildx build --platform linux/amd64 --tag {args.image} --push .")
    print()
    print("# Public image manifest/architecture check")
    print(f"docker buildx imagetools inspect {args.image}")
    print()
    print("# Pull and mounted-IO smoke test")
    print(f"docker pull {args.image}")
    print(
        "docker run --rm --platform linux/amd64 "
        "-v \"$PWD/local_test/input:/input:ro\" "
        "-v \"$PWD/local_test/output:/output\" "
        f"{args.image}"
    )
    print("python3 scripts/validate_submission_io.py local_test/output/results.json")
    print()
    print("# Record image tag and digest in docs/official-submission-log.md before submitting.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
