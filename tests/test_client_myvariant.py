import pytest

from clineval.pipeline.clients.myvariant_client import MyVariantClient


class _FakeMV:
    def __init__(self, res):
        self.res = res

    def set_caching(self):
        pass

    def getvariant(self, _id, fields=None):
        return self.res


def test_myvariant_lookup_backfills_rsid_and_xrefs():
    mv = _FakeMV({"dbsnp": {"rsid": "rs118192172"}, "clinvar": {"rcv": []}, "gnomad_genome": {"af": {}}})
    out = MyVariantClient(mv=mv).lookup("NM_000540.3:c.1840C>T")
    assert out["rsid"] == "rs118192172"
    assert out["clinvar"] == {"rcv": []}
    assert out["gnomad"] == {"af": {}}


def test_myvariant_lookup_handles_missing_fields():
    out = MyVariantClient(mv=_FakeMV({})).lookup("x")   # empty response
    assert out == {"rsid": None, "clinvar": None, "gnomad": None}


def test_myvariant_lookup_passes_assembly_when_given():
    calls = {}

    class _MV:
        def set_caching(self):
            pass

        def getvariant(self, _id, fields=None, assembly=None):
            calls["assembly"] = assembly
            return {"dbsnp": {"rsid": "rsZ"}}

    out = MyVariantClient(mv=_MV()).lookup("chr19:g.38457545C>T", assembly="hg38")
    assert out["rsid"] == "rsZ" and calls["assembly"] == "hg38"


def test_myvariant_lookup_raises_on_error():
    # Transport failure propagates so Stage 1 records "myvariant unavailable" distinctly
    # from a successful lookup that simply found no rsID.
    class _Boom:
        def set_caching(self):
            pass

        def getvariant(self, _id, fields=None):
            raise RuntimeError("network down")

    with pytest.raises(RuntimeError, match="network down"):
        MyVariantClient(mv=_Boom()).lookup("x")


def test_myvariant_default_constructs_real_client(monkeypatch):
    # mv=None -> constructs myvariant.MyVariantInfo() and enables caching.
    import myvariant

    created = {"caching": False}

    class FakeInfo:
        def set_caching(self):
            created["caching"] = True

        def getvariant(self, _id, fields=None):
            return {"dbsnp": {"rsid": "rsX"}}

    monkeypatch.setattr(myvariant, "MyVariantInfo", FakeInfo)
    out = MyVariantClient().lookup("v")
    assert created["caching"] and out["rsid"] == "rsX"


def test_myvariant_default_client_survives_caching_unavailable(monkeypatch):
    # set_caching() needs optional biothings deps; if they're absent it raises — the client
    # must run UNCACHED rather than crash the whole live run (this broke a real live run).
    import myvariant

    class FakeInfo:
        def set_caching(self):
            raise RuntimeError("caching requires biothings_client[caching]")

        def getvariant(self, _id, fields=None):
            return {"dbsnp": {"rsid": "rsY"}}

    monkeypatch.setattr(myvariant, "MyVariantInfo", FakeInfo)
    out = MyVariantClient().lookup("v")   # must not raise
    assert out["rsid"] == "rsY"
