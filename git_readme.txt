git remote add origin https://github.com/ramahozo/dev-test.git
git branch -M main

git branch
git branch --show-current

git switch main
git add --all
git commit -m "commit"
git pull --rebase origin main
git push -u origin main

# Untrack all files in the current branch
git rm -r --cached .