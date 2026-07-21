from clineval.pipeline.synonyms import AA_3TO1, protein_variants, vcf_form


def test_protein_variants_cover_naming_styles():
    # Exact set: pins that dedup works and no unexpected extra form is emitted.
    assert set(protein_variants("NP_000531.2:p.(Arg614Cys)")) == {
        "Arg614Cys", "R614C",                                # bare 3- and 1-letter
        "p.Arg614Cys", "p.R614C",                            # with p.
        "p.(Arg614Cys)", "p.(R614C)",                        # with parens
        "NP_000531.2:p.Arg614Cys", "NP_000531.2:p.R614C",    # accession-prefixed, no parens
        "NP_000531.2:p.(Arg614Cys)", "NP_000531.2:p.(R614C)",  # accession-prefixed, parens
    }


def test_protein_variants_accept_single_letter_input():
    out = set(protein_variants("NP_000531.2:p.(R614C)"))
    assert "p.Arg614Cys" in out and "R614C" in out           # 1-letter in -> 3-letter out too


def test_protein_variants_accept_bare_input_without_accession():
    out = set(protein_variants("p.Arg614Cys"))
    assert "R614C" in out and "p.(R614C)" in out
    assert not any(f.startswith("NP_") for f in out)          # no accession forms invented


def test_protein_variants_handle_stop_gain():
    out = set(protein_variants("NP_000531.2:p.(Arg614Ter)"))
    assert "Arg614Ter" in out and "R614*" in out
    # The '*' input shape yields the identical set (Ter <-> *).
    assert set(protein_variants("NP_000531.2:p.(Arg614*)")) == out


def test_protein_variants_reject_non_substitutions():
    # Frameshift / in-frame del / synonymous / garbage must NOT yield a (wrong) missense form.
    assert protein_variants("NP_000531.2:p.(Arg28Glyfs*16)") == []   # frameshift
    assert protein_variants("NP_000531.2:p.(Arg614=)") == []          # synonymous
    assert protein_variants("NP_000531.2:p.(Arg614_Cys615del)") == [] # in-frame del
    assert protein_variants("p.Xaa1Ybb") == []                        # regex-shaped but not real AAs
    assert protein_variants("") == []
    assert protein_variants("not a variant") == []


def test_amino_acid_table_is_complete():
    assert len(AA_3TO1) == 21                                 # 20 amino acids + Ter
    # Full set of 1-letter codes (catches a transposed/duplicated letter typo).
    assert set(AA_3TO1.values()) == set("ARNDCQEGHILKMFPSTWYV*")
    assert AA_3TO1["Arg"] == "R" and AA_3TO1["Ter"] == "*"


def test_vcf_form():
    assert vcf_form("19", "38457545", "C", "T") == "19-38457545-C-T"
