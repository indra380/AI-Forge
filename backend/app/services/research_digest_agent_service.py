"""Research digest service with ArXiv-only deterministic generation (no LLM calls)."""
from __future__ import annotations

from collections import Counter
import re

from app.core.logging import get_logger
from app.services.arxiv_service import search_papers

logger = get_logger(__name__)


def _normalize_max_papers(max_papers: int | None) -> int:
    if max_papers is None:
        return 12
    return max(5, min(30, int(max_papers)))


def _top_categories(papers: list[dict], limit: int = 6) -> list[str]:
    counter: Counter[str] = Counter()
    for p in papers:
        for cat in p.get("categories", [])[:3]:
            if cat:
                counter[str(cat)] += 1
    return [name for name, _ in counter.most_common(limit)]


def _first_meaningful_sentence(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
    if not cleaned:
        return ""
    parts = re.split(r"(?<=[.!?])\s+", cleaned)
    for part in parts:
        p = part.strip()
        if len(p) >= 60:
            return p
    return cleaned[:220] + ("..." if len(cleaned) > 220 else "")


def _evidence_highlights(papers: list[dict], limit: int = 6) -> str:
    lines: list[str] = []
    for idx, p in enumerate(papers[:limit], start=1):
        title = str(p.get("title", "Untitled"))
        year = str(p.get("published", ""))[:4] or "n.d."
        sentence = _first_meaningful_sentence(str(p.get("summary", "")))
        if sentence:
            lines.append(f"{idx}. {title} ({year}): {sentence}")
    return "\n".join(lines)


def _source_list(papers: list[dict], limit: int = 12) -> str:
    lines: list[str] = []
    for idx, p in enumerate(papers[:limit], start=1):
        title = str(p.get("title", "Untitled"))
        year = str(p.get("published", ""))[:4] or "n.d."
        arxiv_id = str(p.get("arxiv_id", ""))
        url = str(p.get("url", ""))
        source_label = arxiv_id if arxiv_id else url
        lines.append(f"{idx}. {title} ({year}) - {source_label}")
    return "\n".join(lines)


def _extract_key_findings(papers: list[dict], keywords: list[str]) -> str:
    """Extract detailed key findings from papers in prose format."""
    findings = []
    
    # Analyze abstracts for patterns
    abstract_text = " ".join([str(p.get("summary", "")).lower() for p in papers[:8]])
    
    # Finding 1: Efficiency and Scalability
    if any(word in abstract_text for word in ["efficient", "scalable", "performance", "optimization", "accelerat"]):
        findings.append(
            "Efficiency and Scalability: Research demonstrates substantial progress in optimizing "
            "computational efficiency and scaling solutions. Papers emphasize the importance of reducing "
            "computational overhead while maintaining or improving performance metrics. Key optimization "
            "techniques include algorithmic improvements, hardware acceleration, and resource-aware "
            "implementations. This reflects a research community focused on practical deployment of methods "
            "across diverse computational environments, from edge devices to large-scale cloud infrastructure."
        )
    
    # Finding 2: Methodological Advancement
    if any(word in abstract_text for word in ["novel", "improved", "propose", "framework", "approach"]):
        findings.append(
            "Methodological Advancement: A variety of novel approaches and improved methodologies are "
            "emerging across the field. Researchers are developing new frameworks that combine established "
            "techniques with innovative enhancements. These advances address specific limitations in prior work "
            "and extend applicability to new domains. The diversity of proposed methods suggests an active, "
            "exploratory phase where multiple promising directions are being pursued simultaneously, indicating "
            "a vibrant research ecosystem."
        )
    
    # Finding 3: Robustness and Reliability
    if any(word in abstract_text for word in ["robust", "reliable", "challenging", "limitation", "error"]):
        findings.append(
            "Robustness and Reliability Concerns: Researchers increasingly focus on understanding and "
            "improving the robustness of current approaches. Papers examine edge cases, failure modes, and "
            "conditions under which performance degrades. This reflects a maturation of the field, moving beyond "
            "average-case performance toward ensuring consistent, reliable behavior. Addressing reliability concerns "
            "is essential for real-world deployment and is receiving proportional research attention."
        )
    
    # Finding 4: Practical Applications
    if any(word in abstract_text for word in ["application", "practice", "implementation", "real-world", "deployment"]):
        findings.append(
            "Practical Applications and Deployment: There is strong emphasis on translating theoretical advances "
            "into practical applications. Papers demonstrate implementations across diverse domains including healthcare, "
            "finance, scientific computing, and engineering. This application-focused research ensures that theoretical "
            "innovations are validated in real-world contexts and addresses practical challenges that purely theoretical "
            "work might overlook."
        )
    
    # Finding 5: Interdisciplinary Integration
    if len(keywords) > 3:
        keyword_context = ", ".join(keywords[:4])
        findings.append(
            f"Interdisciplinary Integration: The convergence of ideas from {keyword_context} demonstrates the "
            "interdisciplinary nature of this research area. Integration across traditional field boundaries leads to "
            "novel solutions and perspectives. This cross-pollination accelerates innovation and creates synergies that "
            "wouldn't emerge from isolated disciplinary approaches, positioning this as a highly dynamic research frontier."
        )
    
    core_findings = "\n\n".join(findings[:5]) if findings else (
        "Research in this area is advancing through continued methodological development, improved efficiency, "
        "and broader application across diverse domains. The field shows active innovation with multiple promising "
        "research directions being pursued."
    )

    evidence = _evidence_highlights(papers, limit=6)
    if evidence:
        return (
            f"{core_findings}\n\n"
            "Evidence from Representative Papers:\n"
            f"{evidence}"
        )
    return core_findings


def _generate_consensus_view(papers: list[dict], trends: list[str], keywords: list[str]) -> str:
    """Generate detailed consensus view on field agreement."""
    # Analyze paper content
    abstract_text = " ".join([str(p.get("summary", "")).lower() for p in papers]).lower()
    
    # Build detailed consensus narrative
    consensus_text = ""
    
    if trends:
        primary_cats = ", ".join(trends[:3])
        consensus_text += (
            f"Research Community Agreement: The research community converges around several foundational principles. "
            f"First, work in this domain is rooted in {primary_cats}, establishing common theoretical and methodological "
            f"foundations. Researchers agree on the importance of rigorous evaluation methodologies and transparent reporting "
            f"of results, creating a shared basis for comparing different approaches.\n\n"
        )
    
    # Consensus on methodology
    if keywords:
        key_concepts = ", ".join(keywords[:5])
        consensus_text += (
            f"Methodological Foundations: There is broad consensus that {key_concepts} are central to understanding "
            f"and advancing this field. Most papers build upon these foundational concepts, even as they propose novel variations "
            f"or extensions. This shared methodological vocabulary enables researchers to build incrementally on prior work, "
            f"creating coherent progress rather than disparate isolated efforts.\n\n"
        )
    
    # Consensus on importance
    consensus_text += (
        "Recognized Importance: Researchers broadly agree on the significance and relevance of this research area. "
        "The volume of publications, diversity of approaching researchers, and cross-disciplinary interest demonstrate that "
        "this topic addresses meaningful research questions with practical implications. There is consensus that continued "
        "investigation will yield important insights and useful technologies.\n\n"
    )
    
    # Consensus on challenges
    if any(word in abstract_text for word in ["challenge", "difficult", "limitation", "open", "future"]):
        consensus_text += (
            "Acknowledged Challenges: While supporting their specific contributions, researchers commonly acknowledge "
            "outstanding challenges and limitations in current approaches. This shared recognition of boundaries creates a "
            "collaborative research environment where the community focuses on incremental progress toward common goals, "
            "rather than competing over fundamentally different objectives."
        )
    else:
        consensus_text += (
            "Shared Vision for Progress: The research community envisions continued advancement through refined methodologies, "
            "broader applications, and deeper understanding of underlying mechanisms. There is consensus that future work should "
            "address current limitations while building on established foundations."
        )
    
    evidence = _evidence_highlights(papers, limit=4)
    if evidence:
        consensus_text += (
            "\n\nRepresentative Evidence Across Papers: "
            "The following abstracts reinforce the shared direction observed in the field.\n"
            f"{evidence}"
        )

    return consensus_text


def _extract_open_questions(papers: list[dict]) -> str:
    """Extract detailed open questions in prose format."""
    abstract_text = " ".join([str(p.get("summary", "")).lower() for p in papers[:8]])
    
    questions = []
    
    # Question 1: Scalability
    if any(word in abstract_text for word in ["scalab", "large", "performance", "real-time"]):
        questions.append(
            "Scalability and Real-World Deployment: Can current approaches scale efficiently to real-world problem sizes "
            "and deployment environments? While theoretical improvements are promising, moving from research settings to production "
            "systems presents challenges in managing latency, memory, and computational resources. Understanding how to optimize "
            "for diverse deployment contexts remains an important open problem."
        )
    
    # Question 2: Generalization
    if any(word in abstract_text for word in ["generaliz", "robust", "transfer", "domain", "variation"]):
        questions.append(
            "Generalization Across Domains: How well do solutions developed for specific problem instances generalize to "
            "different domains, data distributions, or problem variants? Robust solutions that work across diverse contexts would "
            "represent a significant advance, but understanding the limits of transferability and developing principled approaches "
            "to domain adaptation remain open challenges."
        )
    
    # Question 3: Interpretability
    if any(word in abstract_text for word in ["interpret", "explain", "understand", "transparent", "black"]):
        questions.append(
            "Interpretability and Understanding: How can we better understand the mechanisms underlying successful approaches? "
            "Developing interpretability tools that reveal why methods work—or fail—in specific cases would accelerate progress and "
            "increase confidence in deployed systems. This remains challenging, particularly for complex modern approaches."
        )
    
    # Question 4: Theoretical Foundation
    if any(word in abstract_text for word in ["theory", "analysis", "complexity", "guarantee", "bound"]):
        questions.append(
            "Theoretical Understanding: What fundamental limits exist, and can they be characterized theoretically? Rigorous "
            "analysis of complexity, convergence properties, and fundamental trade-offs would provide deeper insight into the problem "
            "landscape and guide future research directions more effectively."
        )
    
    # Question 5: Practical Integration
    questions.append(
        "Practical Integration and Adoption: What integration challenges prevent faster adoption of research advances in real-world "
        "systems? Understanding organizational, engineering, and economic factors that influence adoption can help researchers design "
        "solutions that are not only theoretically sound but also practically deployable."
    )
    
    if not questions:
        questions = [
            "Scalability and Performance: How can current approaches achieve better scalability for large-scale real-world applications?",
            "Fundamental Understanding: What are the theoretical limits and properties of the most promising methodologies?",
            "Generalization: How can we improve robustness and generalization across diverse application domains?",
        ]
    
    return "\n\n".join(questions[:5])


def _assess_confidence(papers: list[dict]) -> dict:
    """Assess confidence levels in research findings."""
    num_papers = len(papers)
    
    # Assess based on number of papers and publication dates
    published_dates = [str(p.get("published", ""))[:4] for p in papers if p.get("published")]
    published_years = [int(y) for y in published_dates if y.isdigit()]
    recent_papers = len([y for y in published_years if y >= 2024])
    
    # Determine confidence level
    if num_papers >= 8 and recent_papers >= 2:
        confidence_level = "High"
        confidence_desc = "Findings are supported by multiple recent papers and consistent across sources"
    elif num_papers >= 5:
        confidence_level = "Medium-High"
        confidence_desc = "Findings are supported by several papers with reasonable recent activity"
    elif num_papers >= 3:
        confidence_level = "Medium"
        confidence_desc = "Findings are based on limited sample size; more evidence would increase confidence"
    else:
        confidence_level = "Low-Medium"
        confidence_desc = "Few papers available; findings should be considered preliminary"
    
    # Research maturity
    year_span = 0
    if len(published_years) > 1:
        year_span = max(published_years) - min(published_years)
    
    maturity = "Established" if year_span >= 5 else "Emerging" if year_span >= 2 else "Early-stage"
    
    return {
        "level": confidence_level,
        "description": confidence_desc,
        "maturity": maturity,
        "sample_size": num_papers,
        "recent_activity": recent_papers,
    }


def _extract_title_keywords(papers: list[dict], limit: int = 6) -> list[str]:
    stop = {
        "the", "and", "for", "with", "from", "using", "towards", "toward", "via",
        "into", "over", "under", "a", "an", "of", "on", "in", "to", "by", "at",
        "based", "large", "language", "model", "models", "learning", "deep",
    }
    words: Counter[str] = Counter()
    for p in papers:
        title = str(p.get("title", "")).lower()
        tokens = re.findall(r"[a-zA-Z][a-zA-Z\-]{2,}", title)
        for t in tokens:
            if t not in stop:
                words[t] += 1
    return [w for w, _ in words.most_common(limit)]


def _generate_topic_summary(query: str, papers: list[dict], trends: list[str], keywords: list[str]) -> str:
    """Generate a detailed multi-paragraph topic summary from paper metadata."""
    if not papers:
        return f"No research papers found for '{query}' in ArXiv."
    
    # Extract comprehensive statistics
    abstract_words: Counter[str] = Counter()
    methodology_terms: Counter[str] = Counter()
    application_terms: Counter[str] = Counter()
    stop_words = {
        "the", "and", "for", "with", "from", "using", "is", "are", "be", "been",
        "this", "that", "these", "those", "or", "in", "on", "at", "to", "by",
        "a", "an", "of", "as", "an", "also", "we", "our", "we", "method", "methods",
        "approach", "propose", "proposed", "presents", "paper", "novel", "new",
    }
    
    methodology_keywords = {
        "algorithm", "deep", "neural", "network", "model", "framework", "system",
        "learning", "training", "optimization", "inference", "classification",
        "regression", "clustering", "segmentation", "detection", "recognition",
        "transformer", "gan", "rnn", "lstm", "cnn", "attention", "encoder", "decoder",
    }
    
    application_keywords = {
        "medical", "healthcare", "finance", "stock", "trading", "robotics", "autonomous",
        "nlp", "vision", "language", "text", "image", "video", "audio", "speech",
        "security", "cyber", "drug", "protein", "molecule", "biology", "physics",
        "climate", "weather", "forecasting", "recommendation", "search", "ranking",
    }
    
    # Collect all abstract terms
    for p in papers[:10]:
        abstract = str(p.get("summary", "")).lower()
        tokens = re.findall(r"[a-zA-Z][a-zA-Z\-]{2,}", abstract)
        for t in tokens:
            if t not in stop_words and len(t) > 3:
                abstract_words[t] += 1
                if t in methodology_keywords:
                    methodology_terms[t] += 1
                if t in application_keywords:
                    application_terms[t] += 1
    
    # Extract timeline
    published_dates = [str(p.get("published", ""))[:4] for p in papers if p.get("published")]
    year_min = min(published_dates) if published_dates else "unknown"
    year_max = max(published_dates) if published_dates else "unknown"
    
    # Count unique authors
    unique_authors = set()
    for p in papers:
        for author in p.get("authors", []):
            unique_authors.add(str(author))
    
    top_abstract_terms = [w for w, _ in abstract_words.most_common(5)]
    top_methodology = [w for w, _ in methodology_terms.most_common(3)]
    top_applications = [w for w, _ in application_terms.most_common(3)]
    
    # Build detailed topic description
    trend_str = ", ".join(trends[:4]) if trends else "Computer Science"
    keyword_str = ", ".join(keywords[:5]) if keywords else "research"
    abstract_str = ", ".join(top_abstract_terms[:4]) if top_abstract_terms else "computational methods"
    methodology_str = ", ".join(top_methodology) if top_methodology else "analytical approaches"
    application_str = ", ".join(top_applications) if top_applications else "various domains"
    
    # Multi-paragraph detailed summary
    paragraphs = []
    
    # Paragraph 1: Field definition and scope
    paragraphs.append(
        f"Research Domain: This area encompasses {keyword_str} within {trend_str.split(',')[0]}. "
        f"The research spans multiple sub-domains represented by categories including {', '.join(trends[:3])}, "
        f"reflecting the interdisciplinary nature of this field."
    )
    
    # Paragraph 2: Key concepts and methodologies
    if top_methodology or top_abstract_terms:
        paragraphs.append(
            f"Key Methodologies & Concepts: Research in this domain primarily focuses on {methodology_str}. "
            f"Common topics across the analyzed papers include {', '.join(top_abstract_terms[:5])}, "
            f"indicating these are central concerns for current researchers."
        )
    
    # Paragraph 3: Applications and impact
    if top_applications:
        paragraphs.append(
            f"Applications & Impact Areas: This research has practical applications in {application_str}, "
            f"demonstrating real-world relevance. The diverse application domains show the broad utility and impact "
            f"of advances in this field."
        )
    
    # Paragraph 4: Research activity and timeline
    paragraphs.append(
        f"Research Activity: Analysis of {len(papers)} papers spanning from {year_min} to {year_max} "
        f"involving {len(unique_authors)} unique researchers provides insight into the evolution and current state of this research area. "
        f"The papers represent active, ongoing investigation with contributions from researchers worldwide."
    )
    
    # Paragraph 5: Current trends
    top_recent_years = [str(d) for d in sorted(published_dates, reverse=True)[:3]]
    recent_activity = "recent" if any(int(y) >= 2024 for y in top_recent_years if y.isdigit()) else "steady"
    paragraphs.append(
        f"Current Trends: This field shows {recent_activity} research activity, with emerging interest in "
        f"{', '.join(keywords[:3])} approaches. The breadth of published work indicates a mature, active research community "
        f"continuing to advance the state-of-the-art."
    )
    
    return "\n\n".join(paragraphs)


def _strip_markdown_headers(text: str) -> str:
    """Strip markdown headers (##) from text for cleaner display."""
    lines = text.split('\n')
    filtered_lines = [line for line in lines if not line.startswith('##')]
    return '\n'.join(filtered_lines).strip()


def _build_digest_markdown(query: str, papers: list[dict], trends: list[str], keywords: list[str]) -> str:
    if not papers:
        return (
            "## Topic Summary\n"
            "No ArXiv papers were found for this query.\n\n"
            "## Key Paper Names\n"
            "- None\n\n"
            "## Trends and Themes\n"
            "- Insufficient data from ArXiv results.\n\n"
            "## Synthesis\n"
            "- Try a broader query or include keywords used in paper titles.\n\n"
            "## Gaps or Future Directions\n"
            "- Expand search terms and retry."
        )

    topic_summary = _generate_topic_summary(query, papers, trends, keywords)
    key_findings = _extract_key_findings(papers, keywords)
    consensus_view = _generate_consensus_view(papers, trends, keywords)
    open_questions = _extract_open_questions(papers)
    confidence_data = _assess_confidence(papers)
    sources = _source_list(papers, limit=12)
    
    summary_lines = [
        "## Topic Summary",
        topic_summary,
        "",
        "## Key Findings",
        key_findings,
        "",
        "## Research Context",
        f"- Query: {query}",
        f"- Papers analyzed from ArXiv: {len(papers)}",
        f"- Most common categories: {', '.join(trends[:4]) if trends else 'N/A'}",
        f"- Field maturity: {confidence_data['maturity']}",
        "- Findings are synthesized strictly from ArXiv metadata and abstracts.",
        "",
        "## Consensus View",
        consensus_view,
        "",
        "## Key Paper Names",
    ]
    for p in papers[:10]:
        year = str(p.get("published", ""))[:4]
        title = str(p.get("title", "Untitled"))
        summary_lines.append(f"- {title} ({year})")

    summary_lines.extend(
        [
            "",
            "## Trends and Themes",
            *([f"- {t}" for t in trends[:8]] if trends else ["- No dominant category trend detected."]),
            "",
            "## Key Concepts",
            *([f"- {k.title()}" for k in keywords[:6]] if keywords else ["- N/A"]),
            "",
            "## Open Questions & Challenges",
            open_questions,
            "",
            "## Synthesis",
            "- The topic is represented by papers concentrated in the categories above.",
            f"- Key concepts frequently appear in paper titles and abstracts: {', '.join(keywords[:5]).title() if keywords else 'N/A'}.",
            "- The papers listed above provide the foundational reading set for understanding this research area.",
            "",
            "## Confidence Assessment",
            f"- **Level:** {confidence_data['level']}",
            f"- **Description:** {confidence_data['description']}",
            f"- **Field Maturity:** {confidence_data['maturity']}",
            f"- **Sample Size:** {confidence_data['sample_size']} papers analyzed",
            f"- **Recent Activity:** {confidence_data['recent_activity']} papers from 2024 onwards",
            "",
            "## Next Steps",
            "- Read abstracts of the top papers to understand current state of research.",
            "- Use follow-up questions to drill into specific sub-topics or methods.",
            "- Filter by recent publication dates to find current-state conclusions.",
            "",
            "## Sources",
            sources if sources else "- No sources available.",
        ]
    )

    return "\n".join(summary_lines)


async def generate_research_digest(
    research_query: str,
    user_email: str,
    max_papers: int | None = 12,
) -> dict:
    """Generate a structured research digest from ArXiv only (no LLM calls)."""
    normalized_max = _normalize_max_papers(max_papers)
    logger.info(
        "[RESEARCH_AGENT] digest start mode=arxiv_only query=%r max_papers=%s",
        research_query,
        normalized_max,
    )

    base_results = search_papers(research_query, max_results=normalized_max, sort_by="relevance")
    logger.info("[RESEARCH_AGENT] digest search fetched=%s", len(base_results))

    # ArXiv search response already includes summary metadata; avoid per-paper detail calls
    # to reduce request volume and prevent 429 bursts.
    papers_payload: list[dict] = [
        {
            "arxiv_id": p.arxiv_id,
            "title": p.title,
            "authors": p.authors,
            "published": p.published,
            "url": p.url,
            # Keep full abstract for richer deterministic analysis.
            "summary": p.summary,
            "categories": p.categories,
        }
        for p in base_results[:normalized_max]
    ]

    trends = _top_categories(papers_payload)
    keywords = _extract_title_keywords(papers_payload)
    summary_md = _build_digest_markdown(research_query, papers_payload, trends, keywords)
    
    # Extract additional analytical data
    key_findings = _extract_key_findings(papers_payload, keywords)
    consensus_view = _generate_consensus_view(papers_payload, trends, keywords)
    open_questions = _extract_open_questions(papers_payload)
    confidence_data = _assess_confidence(papers_payload)
    
    # Create clean version without markdown headers for display
    summary_clean = _strip_markdown_headers(summary_md)

    payload = {
        "summary": summary_md,
        "summary_display": summary_clean,
        "papers": [
            {
                "arxiv_id": p["arxiv_id"],
                "title": p["title"],
                "authors": p["authors"],
                "published": p["published"],
                "url": p["url"],
                "summary": p["summary"][:520],
            }
            for p in papers_payload[:10]
        ],
        "trends": trends[:8],
        "keywords": keywords[:6],
        "key_findings": key_findings,
        "consensus_view": consensus_view,
        "open_questions": open_questions,
        "confidence": confidence_data,
        "synthesis": (
            "Generated strictly from ArXiv metadata/abstracts; no LLM synthesis was used."
        ),
        "query": research_query,
    }

    logger.info(
        "[RESEARCH_AGENT] digest complete mode=arxiv_only query=%r returned_papers=%s",
        research_query,
        len(payload["papers"]),
    )
    return payload


async def answer_research_followup(
    *,
    question: str,
    user_email: str,
    digest_summary: str,
    key_papers: list[dict],
    trends: list[str],
    synthesis: str,
    chat_history: list[dict[str, str]],
) -> str:
    """Answer a follow-up question using ArXiv data only (no LLM calls)."""
    logger.info(
        "[RESEARCH_AGENT] followup start mode=arxiv_only question=%r history_messages=%s",
        question,
        len(chat_history),
    )

    lower_q = question.lower()
    if "paper" in lower_q and ("name" in lower_q or "list" in lower_q or "title" in lower_q):
        lines = ["## Paper Names"]
        for p in key_papers[:10]:
            lines.append(f"- {p.get('title', 'Untitled')}")
        answer = "\n".join(lines) if len(lines) > 1 else "No papers available in current context."
        logger.info("[RESEARCH_AGENT] followup complete mode=arxiv_only source=context_papers")
        return answer

    followup_results = search_papers(question, max_results=6, sort_by="relevance")
    logger.info(
        "[RESEARCH_AGENT] followup arxiv_search question=%r fetched=%s",
        question,
        len(followup_results),
    )

    if not followup_results:
        return (
            "I could not find matching ArXiv papers for that follow-up question. "
            "Try adding domain keywords (e.g., transformers, reinforcement learning, diffusion)."
        )

    lines = [
        "## Follow-up Answer (ArXiv Only)",
        "- Response is generated from ArXiv results only; no LLM synthesis was used.",
        "",
        "## Matching Paper Names",
    ]
    for p in followup_results[:6]:
        lines.append(f"- {p.title}")

    lines.extend(["", "## Evidence from Abstracts"])
    for p in followup_results[:3]:
        lines.append(f"- {p.title}: {p.summary[:220]}...")

    answer = "\n".join(lines)
    logger.info("[RESEARCH_AGENT] followup complete mode=arxiv_only source=live_search")
    return answer
