import Image from 'next/image'

interface Props {
  size?: number
  showText?: boolean
  textSize?: string   // tailwind text-* class
  className?: string
}

export default function OneGoalLogo({
  size = 28,
  showText = true,
  textSize = 'text-xl',
  className = '',
}: Props) {
  return (
    <div className={`flex items-center gap-2.5 ${className}`}>
      <Image
        src="/logo-icon.jpeg"
        alt="One Goal"
        width={size}
        height={size}
        style={{ objectFit: 'contain', flexShrink: 0 }}
        priority
      />
      {showText && (
        <span className={`font-display ${textSize} text-[#F5F1ED] leading-none`}>
          One Goal
        </span>
      )}
    </div>
  )
}
