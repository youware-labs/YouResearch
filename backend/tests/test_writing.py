"""
Integration tests for Writing Intelligence features.
"""

import asyncio
import tempfile
from pathlib import Path
import pytest


@pytest.fixture
def test_project():
    """Create a temporary test project."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Main document
        (Path(tmpdir) / "main.tex").write_text(r"""
\documentclass{article}
\usepackage{amsmath,graphicx}
\usepackage[backend=biber]{biblatex}
\addbibresource{refs.bib}

\begin{document}

\section{Introduction}
\label{sec:intro}
Deep learning has transformed AI \cite{lecun2015deep}.
Transformers \cite{vaswani2017attention} are particularly important.

\subsection{Contributions}
We make three contributions.

\section{Related Work}
\label{sec:related}
Prior work includes BERT \cite{devlin2019bert}.

\begin{table}[htbp]
    \caption{Results}
    \label{tab:results}
    \begin{tabular}{lc}
        Model & Score \\
        Ours & 95.2 \\
    \end{tabular}
\end{table}

\begin{figure}[htbp]
    \centering
    \caption{Architecture}
\end{figure}

\section{Conclusion}
We did great work.

\end{document}
""")

        # Bibliography
        (Path(tmpdir) / "refs.bib").write_text("""
@article{lecun2015deep,
    title={Deep Learning},
    author={LeCun, Yann and Bengio, Yoshua and Hinton, Geoffrey},
    journal={Nature},
    year={2015}
}

@article{vaswani2017attention,
    title={Attention Is All You Need},
    author={Vaswani, Ashish and others},
    journal={NeurIPS},
    year={2017}
}

@article{devlin2019bert,
    title={BERT: Pre-training of Deep Bidirectional Transformers},
    author={Devlin, Jacob and others},
    booktitle={NAACL},
    year={2019}
}

@article{unused2020,
    title={This Paper Is Never Cited},
    author={Nobody, Someone},
    year={2020}
}
""")

        yield tmpdir


class TestLatexParser:
    """Test LaTeX parsing functionality."""

    def test_parse_sections(self, test_project):
        from services.latex_parser import parse_document

        content = (Path(test_project) / "main.tex").read_text()
        structure = parse_document(content)

        assert len(structure.sections) == 4  # Intro, Contributions, Related, Conclusion
        assert structure.sections[0].name == "Introduction"
        assert structure.sections[0].label == "sec:intro"

    def test_parse_elements(self, test_project):
        from services.latex_parser import parse_document

        content = (Path(test_project) / "main.tex").read_text()
        structure = parse_document(content)

        assert len(structure.elements) == 2  # table and figure

        table = next(e for e in structure.elements if e.type == "table")
        assert table.label == "tab:results"
        assert "Results" in table.caption

    def test_parse_citations(self, test_project):
        from services.latex_parser import parse_document

        content = (Path(test_project) / "main.tex").read_text()
        structure = parse_document(content)

        assert len(structure.citations) == 3  # lecun, vaswani, devlin
        keys = {c.key for c in structure.citations}
        assert "lecun2015deep" in keys
        assert "vaswani2017attention" in keys

    def test_detect_citation_style(self, test_project):
        from services.latex_parser import parse_document

        content = (Path(test_project) / "main.tex").read_text()
        structure = parse_document(content)

        assert structure.citation_style == "biblatex"
        assert structure.bib_file == "refs.bib"

    def test_find_unused_citations(self, test_project):
        from services.latex_parser import (
            parse_document, parse_bib_file_path, find_unused_citations
        )

        content = (Path(test_project) / "main.tex").read_text()
        structure = parse_document(content)

        bib_entries = parse_bib_file_path(Path(test_project) / "refs.bib")
        unused = find_unused_citations(structure.citations, bib_entries)

        assert len(unused) == 1
        assert unused[0].key == "unused2020"


class TestCitationTools:
    """Test citation generation tools."""

    def test_generate_cite_key(self):
        from agent.tools.citations import PaperMetadata, generate_cite_key

        paper = PaperMetadata(
            title="Attention Is All You Need",
            authors=["Vaswani, Ashish", "Shazeer, Noam"],
            year=2017,
        )

        key = generate_cite_key(paper)
        assert key == "vaswani2017attention"

    def test_generate_bibtex(self):
        from agent.tools.citations import PaperMetadata, generate_bibtex

        paper = PaperMetadata(
            title="Test Paper",
            authors=["Smith, John"],
            year=2024,
            arxiv_id="2401.12345",
        )

        bibtex = generate_bibtex(paper)
        assert "@misc{" in bibtex
        assert "eprint = {2401.12345}" in bibtex
        assert "archivePrefix = {arXiv}" in bibtex


class TestContentGeneration:
    """Test content generation tools."""

    @pytest.mark.asyncio
    async def test_create_table(self):
        from agent.pydantic_agent import create_table, AuraDeps
        from unittest.mock import MagicMock

        ctx = MagicMock()
        ctx.deps = AuraDeps(project_path="/tmp")

        result = await create_table(
            ctx,
            data="Model,Accuracy\nBERT,85.2\nGPT,79.3",
            caption="Test table",
            label="test",
        )

        assert r"\begin{table}" in result
        assert r"\toprule" in result
        assert "BERT" in result
        assert r"\label{tab:test}" in result

    @pytest.mark.asyncio
    async def test_create_figure(self):
        from agent.pydantic_agent import create_figure, AuraDeps
        from unittest.mock import MagicMock

        ctx = MagicMock()
        ctx.deps = AuraDeps(project_path="/tmp")

        result = await create_figure(
            ctx,
            description="Test diagram",
            figure_type="tikz",
            caption="A test figure",
            label="test",
        )

        assert r"\begin{figure}" in result
        assert r"\begin{tikzpicture}" in result
        assert r"\label{fig:test}" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
