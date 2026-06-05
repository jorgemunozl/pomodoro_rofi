import subprocess

result = subprocess.run(
    ["i3-msg", "workspace --no-auto-back-and-forth pomodoro 🍅"],
    capture_output=True,
    text=True,
)
print("stdout:", result.stdout)
print("stderr:", result.stderr)
print("returncode:", result.returncode)
