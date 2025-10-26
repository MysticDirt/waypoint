import React from 'react'
import { Rocket, ArrowRight, CheckCircle, Zap, Database } from 'lucide-react'
import WaypointLogo from './assets/Waypoint_logo.svg'

// Header Component
const Header = () => {
  return (
    <header 
      className="w-full py-4 px-6 bg-background animate-fade-in-down"
      style={{ animationDelay: '100ms' }}
    >
      <div className="container mx-auto flex justify-between items-center">
        {/* Logo */}
        <div className="flex items-center">
          <img src={WaypointLogo} alt="Waypoint" className="h-8" />
        </div>

        {/* Navigation */}
        <nav className="hidden md:flex space-x-8">
          <a 
            href="#features" 
            className="font-mulish text-text-secondary hover:text-brand-primary transition-all duration-300"
          >
            Features
          </a>
          <a 
            href="#pricing" 
            className="font-mulish text-text-secondary hover:text-brand-primary transition-all duration-300"
          >
            Pricing
          </a>
          <a 
            href="#about" 
            className="font-mulish text-text-secondary hover:text-brand-primary transition-all duration-300"
          >
            About
          </a>
        </nav>
      </div>
    </header>
  )
}

// Hero Section Component
const HeroSection = () => {
  return (
    <section 
      className="min-h-[70vh] flex flex-col justify-center items-center text-center px-6 animate-fade-in-down"
      style={{ animationDelay: '300ms' }}
    >
      {/* Main Headline */}
      <h1 className="font-manrope font-extrabold text-6xl text-text-primary max-w-4xl">
        Plan Your Perfect Journey with AI
      </h1>

      {/* Subheading */}
      <p className="font-mulish text-xl text-text-secondary max-w-2xl mt-4">
        Waypoint uses advanced AI to autonomously plan and manage your life activities. 
        From weekend getaways to cultural experiences, we break down your goals and create 
        interactive itineraries with real-time updates.
      </p>

      {/* CTA Group */}
      <div className="mt-8 flex flex-col sm:flex-row gap-4">
        {/* Primary CTA */}
        <a href="/app">
          <button className="bg-brand-primary text-brand-text font-bold font-mulish rounded-lg px-6 py-3 text-lg flex items-center transition-all duration-300 hover:shadow-lg hover:bg-opacity-90">
            Get Started
            <Rocket className="w-5 h-5 ml-2" />
          </button>
        </a>

        {/* Secondary CTA */}
        <a href="#features">
          <button className="border border-text-secondary text-text-secondary font-bold font-mulish rounded-lg px-6 py-3 text-lg flex items-center transition-all duration-300 hover:bg-brand-light hover:border-brand-light hover:text-text-primary">
            Learn More
            <ArrowRight className="w-5 h-5 ml-2" />
          </button>
        </a>
      </div>
    </section>
  )
}

// Features Section Component
const FeaturesSection = () => {
  const features = [
    {
      icon: CheckCircle,
      title: 'AI-Powered Planning',
      description: 'Our intelligent agent autonomously breaks down your goals and creates comprehensive itineraries tailored to your preferences.'
    },
    {
      icon: Zap,
      title: 'Real-Time Updates',
      description: 'Experience instant synchronization between your itinerary and interactive map with live data from multiple sources.'
    },
    {
      icon: Database,
      title: 'Smart Integration',
      description: 'Seamlessly connects with flights, hotels, and events APIs to provide you with the most up-to-date information.'
    }
  ]

  return (
    <section 
      id="features"
      className="py-20 px-6 bg-background animate-fade-in-down"
      style={{ animationDelay: '500ms' }}
    >
      <div className="container mx-auto">
        {/* Title */}
        <h2 className="font-manrope font-bold text-4xl text-text-primary text-center mb-12">
          Our Features
        </h2>

        {/* Features Grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          {features.map((feature, index) => (
            <div 
              key={index}
              className="flex flex-col items-center text-center p-6 rounded-lg hover:shadow-lg transition-all duration-300"
            >
              {/* Icon */}
              <div className="w-12 h-12 rounded-full bg-brand-light flex items-center justify-center mb-4">
                <feature.icon className="w-6 h-6 text-brand-primary" />
              </div>

              {/* Title */}
              <h3 className="font-manrope font-bold text-xl text-text-primary mb-2">
                {feature.title}
              </h3>

              {/* Description */}
              <p className="font-mulish text-text-secondary">
                {feature.description}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

// Footer Component
const Footer = () => {
  return (
    <footer className="py-8 px-6 bg-background border-t border-brand-light">
      <div className="container mx-auto">
        {/* Developer Credits */}
        <p className="font-mulish text-text-secondary text-center text-sm">
          Developed by First Time Hackers: Issac, Leo, and Chandrark
        </p>
      </div>
    </footer>
  )
}

// Main Landing Page Component
const LandingPage = () => {
  return (
    <div className="min-h-screen bg-background">
      <Header />
      <HeroSection />
      <FeaturesSection />
      <Footer />
    </div>
  )
}

export default LandingPage
