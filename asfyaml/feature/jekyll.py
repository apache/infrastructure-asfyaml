import asfyaml
import strictyaml

"""Does something..."""

"""
class ASFJekyllFeature(asfyaml.ASFYamlFeature, name="jekyll", env="production", priority=4):

    schema = strictyaml.Map({"foo": strictyaml.Str(),  })

    def run(self):
         Jekyll auto-build. Sample entry:
              jekyll:
                whoami: applicable branch (optional; 'asf-site' not allowed)
                target: branch (optional)
                theme: name (optional, default: 'theme')
                notify: recipients (optional)
                outputdir: dirname (optional, default: 'output')
        
        # Don't build from asf-site, like...ever
        #ref = get_branch(yml)
        print("Running Jekyll feature...")
        print(self.yaml.foo)
        if True:
            return
        if ref == 'asf-site':
            print("Not auto-building from asf-site, ever...")
            return

        # If whoami specified, ignore this payload if branch does not match
        whoami = yml.get('whoami')
        if whoami and whoami != ref:
            return

        # Get target branch, if any, default to same branch
        target = yml.get('target', ref)

        # Get optional theme
        theme = yml.get('theme', 'theme')

        # Get optional outputdirectory name, Default 'output'
        outputdir = yml.get('outputdir', 'output')

        pname = infer_project_name(cfg)

        # Get notification list
        pnotify = yml.get('notify', cfg.recips[0])

        # Contact buildbot 2
        bbusr, bbpwd = open("/x1/gitbox/auth/bb2.txt").read().strip().split(':', 1)
        s = requests.Session()
        s.get("https://ci2.apache.org/auth/login", auth=(bbusr, bbpwd))

        payload = {
            "method": "force",
            "jsonrpc": "2.0",
            "id": 0,
            "params": {
                "reason": "Triggered jekyll auto-build via .asf.yaml by %s" % cfg.committer,
                "builderid": "7",
                "source": "https://gitbox.apache.org/repos/asf/%s.git" % cfg.repo_name,
                "sourcebranch": ref,
                "outputbranch": target,
                "outputdir": outputdir,
                "project": pname,
                "theme": theme,
                "notify": pnotify,
            }
        }
        print("Triggering jekyll build...")
        s.post('https://ci2.apache.org/api/v2/forceschedulers/jekyll_websites', json=payload)
        print("Done!")

"""
