from asfyaml.asfyaml import ASFYamlFeature
import strictyaml


class ASFTestFeature(ASFYamlFeature, name="test"):
    schema = strictyaml.Map({"foo": strictyaml.Str(), })

    def run(self):
        pass
