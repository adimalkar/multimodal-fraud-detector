import os

def replace_in_file(path, old, new):
    with open(path, 'r') as f:
        content = f.read()
    if old in content:
        content = content.replace(old, new)
        with open(path, 'w') as f:
            f.write(content)
        print(f"Updated {path}")
    else:
        print(f"Could not find '{old}' in {path}")

# Button
replace_in_file(
    'frontend/components/Button/index.tsx',
    'const Button = (props: PropsWithChildren) => {',
    'const Button = (props: PropsWithChildren<{onClick?: () => void, className?: string}>) => {'
)
replace_in_file(
    'frontend/components/Button/index.tsx',
    '<button className="relative',
    '<button onClick={props.onClick} className={`relative ${props.className || ""}`}'
)

# Hero
replace_in_file(
    'frontend/components/Hero/index.tsx',
    'text-center">AI SEO</h1>',
    'text-center" style={{ letterSpacing: "-0.04em", fontSize: "110px" }}>FraudSight AI</h1>'
)
replace_in_file(
    'frontend/components/Hero/index.tsx',
    'Elevate your site&apos;s visibility effortlessly with AI, where smart\n                    technology meets user-friendly SEO tools.',
    'Multi-Agent Insurance Fraud Detection. Zero-trust pipeline powered by Qwen and DeepSeek for Images, Documents, and Video.'
)
replace_in_file(
    'frontend/components/Hero/index.tsx',
    '<Button>Join waitlist</Button>',
    "<Button onClick={() => document.getElementById('app-interface')?.scrollIntoView({ behavior: 'smooth' })}>Start Scanning</Button>"
)

# Header
replace_in_file(
    'frontend/components/Header/index.tsx',
    '<div>AI SEO</div>',
    '<div className="font-bold text-xl tracking-tighter">FraudSight AI</div>'
)

# Features
replace_in_file(
    'frontend/components/Features/index.tsx',
    '"User-friendly dashboard"',
    '"Multi-Modal Support"'
)
replace_in_file(
    'frontend/components/Features/index.tsx',
    '"One-click optimization"',
    '"Agentic Consensus"'
)
replace_in_file(
    'frontend/components/Features/index.tsx',
    '"Smart keyword generator"',
    '"Vision-Language Models"'
)
replace_in_file(
    'frontend/components/Features/index.tsx',
    'Elevate your SEO efforts.',
    'Expose fraud with precision.'
)
replace_in_file(
    'frontend/components/Features/index.tsx',
    'From small startups to large enterprises, our AI-driven tool has\n                    revolutionized the way businesses approach SEO.',
    'From deepfakes to document forgery, our multi-agent architecture uses state-of-the-art vision models and critic agents to detect microscopic anomalies.'
)

# Page
replace_in_file(
    'frontend/app/page.tsx',
    'import Testimonials from "@/components/Testimonials";',
    'import AppInterface from "@/components/AppInterface";\nimport Testimonials from "@/components/Testimonials";'
)
replace_in_file(
    'frontend/app/page.tsx',
    '<Testimonials />',
    '<AppInterface />\n\t\t\t<Testimonials />'
)

# CTA
replace_in_file(
    'frontend/components/CTA/index.tsx',
    'AI-driven SEO for everyone.',
    'Zero-trust verification.'
)
replace_in_file(
    'frontend/components/CTA/index.tsx',
    'Achieve clear, impactful results without the complexity.',
    'Detect synthetic media and tampered documents instantly.'
)
replace_in_file(
    'frontend/components/CTA/index.tsx',
    '<Button>Join waitlist</Button>',
    '<Button>Analyze File Now</Button>'
)
